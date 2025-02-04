from chemprop.data import build_dataloader
from omegaconf import DictConfig
import numpy as np
import pandas as pd
import torch

import src.nn
import src.metrics

from src.model import (
    MPNNDimRed,
    TwoChannelFFN,
    TwoChannelLinear
)

from src.data import (
    RxnRCDataset,
    MFPDataset,
    mfp_build_dataloader,
    RxnRCDatapoint
)
from src.featurizer import (  
    SimpleReactionMolGraphFeaturizer,
    RCVNReactionMolGraphFeaturizer,
    ReactionMorganFeaturizer,
    MultiHotAtomFeaturizer,
    MultiHotBondFeaturizer
)

featurizers = {
    'rxn_simple': (RxnRCDataset, SimpleReactionMolGraphFeaturizer, build_dataloader),
    'rxn_rc': (RxnRCDataset, RCVNReactionMolGraphFeaturizer, build_dataloader),
    'mfp': (MFPDataset, ReactionMorganFeaturizer, mfp_build_dataloader)
}

def construct_featurizer(cfg: DictConfig):
    datapoint_from_smi = RxnRCDatapoint.from_smi
    dataset_base, featurizer_base, generate_dataloader = featurizers[cfg.model.featurizer]
    if cfg.model.featurizer == 'mfp':
        featurizer = featurizer_base(radius=cfg.model.radius, length=cfg.model.vec_len)
    else:
        featurizer = featurizer_base(
            atom_featurizer=MultiHotAtomFeaturizer.no_stereo(),
            bond_featurizer=MultiHotBondFeaturizer()
        )

    return featurizer, datapoint_from_smi, dataset_base, generate_dataloader

def featurize_data(cfg: DictConfig, rng: np.random.Generator, train_data: pd.DataFrame = None, val_data: pd.DataFrame = None):
    featurizer, datapoint_from_smi, dataset_base, generate_dataloader = construct_featurizer(cfg)
    
    if train_data is not None:
        train_datapoints = []
        for _, row in train_data.iterrows():
            y = np.array([row['y']]).astype(np.float32)
            train_datapoints.append(datapoint_from_smi(smarts=row['smarts'], reaction_center=row['reaction_center'], y=y, x_d=row['protein_embedding']))
        
        train_dataset = dataset_base(train_datapoints, featurizer=featurizer)
        train_dataloader = generate_dataloader(train_dataset, shuffle=True, seed=cfg.data.seed)
    else:
        train_dataloader = None

    if val_data is not None:
        val_datapoints = []
        for _, row in val_data.iterrows():
            y = np.array([row['y']]).astype(np.float32)
            val_datapoints.append(datapoint_from_smi(smarts=row['smarts'], reaction_center=row['reaction_center'], y=y, x_d=row['protein_embedding']))

        rng.shuffle(val_datapoints) # Avoid weirdness of calculating metrics with only one class in the batch
        val_dataset = dataset_base(val_datapoints, featurizer=featurizer)
        val_dataloader = generate_dataloader(val_dataset, shuffle=False, batch_size=500)
    else:
        val_dataloader = None

    return train_dataloader, val_dataloader, featurizer

def construct_model(cfg: DictConfig, embed_dim: int, featurizer, device, ckpt=None):
    pos_weight = torch.ones([1]) * cfg.data.neg_multiple * cfg.training.pos_multiplier
    pos_weight = pos_weight.to(device)
    agg = getattr(src.nn, cfg.model.agg)() if cfg.model.agg else None
    pred_head = getattr(src.nn, cfg.model.pred_head)(
        input_dim=cfg.model.d_h_encoder * 2,
        criterion = src.nn.WeightedBCELoss(pos_weight=pos_weight)
    )
    metrics = [getattr(src.metrics, m)() for m in cfg.training.metrics]

    if cfg.model.message_passing:
        dv, de = featurizer.shape
        mp = getattr(src.nn, cfg.model.message_passing)(
            d_v=dv,
            d_e=de,
            d_h=cfg.model.d_h_encoder,
            depth=cfg.model.encoder_depth
        )

    # TODO streamline model api, get rid of LinDimRed
    # NOTE you can use hydra.utils.instantiate and partial to move
    # some of this up to configs
    if cfg.model.model == 'mpnn_dim_red':
        model = MPNNDimRed(
            reduce_X_d=src.nn.LinDimRed(d_in=embed_dim, d_out=cfg.model.d_h_encoder),
            message_passing=mp,
            agg=agg,
            predictor=pred_head,
            metrics=metrics
        )
    elif cfg.model.model == 'ffn':
        model = TwoChannelFFN(
            d_rxn=featurizer.length,
            d_prot=embed_dim,
            d_h=cfg.model.d_h_encoder,
            encoder_depth=cfg.model.encoder_depth,
            predictor=pred_head,
            metrics=metrics
        )
    elif cfg.model.model == 'linear':
        model = TwoChannelLinear(
            d_rxn=featurizer.length,
            d_prot=embed_dim,
            d_h=cfg.model.d_h_encoder,
            predictor=pred_head,
            metrics=metrics
    )
        
    # Load from ckpt
    if ckpt:
        ckpt = torch.load(ckpt, map_location=device)
        model.load_state_dict(ckpt['state_dict'])
        
    return model

def downsample_negatives(data: pd.DataFrame, neg_multiple: int, rng: np.random.Generator):
    neg_idxs = data[data['y'] == 0].index
    n_to_rm = len(neg_idxs) - (len(data[data['y'] == 1]) * neg_multiple)
    idx_to_rm = rng.choice(neg_idxs, n_to_rm, replace=False)
    data.drop(axis=0, index=idx_to_rm, inplace=True)
     