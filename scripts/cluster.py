from sklearn.cluster import AgglomerativeClustering
from src.similarity import rcmcs_similarity_matrix, load_similarity_matrix
from src.utils import load_json, save_json, construct_sparse_adj_mat
import pandas as pd
import numpy as np
from omegaconf import DictConfig
import hydra
from pathlib import Path

@hydra.main(version_base=None, config_path="../configs", config_name="cluster")
def main(cfg: DictConfig):
    adj, adj_to_prot_id, adj_to_rxn_id = construct_sparse_adj_mat(
        Path(cfg.filepaths.data) / cfg.dataset / (cfg.toc + ".csv")
        )
    
    if cfg.similarity_score == 'rcmcs':
        rules = pd.read_csv(
            filepath_or_buffer=Path(cfg.filepaths.artifacts) / 'minimal1224_all_uniprot.tsv',
            sep='\t'
        )
        rules.set_index('Name', inplace=True)
        rxns = load_json(Path(cfg.filepaths.data) / f"{cfg.dataset}/{cfg.toc}.json")
        matrix_idx_to_id = adj_to_rxn_id
        S = rcmcs_similarity_matrix(rxns, rules, matrix_idx_to_id)
    else: # Protein based similarity
        S = load_similarity_matrix(
            sim_path=Path(cfg.filepaths.results) / "similarity_matrices",
            dataset=cfg.dataset,
            toc=cfg.toc,
            sim_metric=cfg.similarity_score
        )
        matrix_idx_to_id = adj_to_prot_id

        if cfg.similarity_score == 'blosum':
            # Normalize blosum alignment scores
            S = np.where(S > cfg.blosum_ub, cfg.blosum_ub, S)
            S = np.where(S < cfg.blosum_lb, cfg.blosum_lb, S)
            S = (S - S.min()) / (S.max() - S.min())
        
    D = 1 - S # Distance matrix
    
    for cutoff in cfg.cutoffs:
        d_cutoff = 1 - (cutoff / 100)

        # Cluster
        ac = AgglomerativeClustering(
            n_clusters=None,
            metric='precomputed',
            distance_threshold=d_cutoff,
            linkage='single'
        )
        ac.fit(D)            
        labels = ac.labels_
        id2cluster = {matrix_idx_to_id[i] : int(labels[i]) for i in matrix_idx_to_id}
        
        # Save clusters
        save_json(id2cluster, Path(cfg.filepaths.clustering) / f"{cfg.dataset}_{cfg.toc}_{cfg.similarity_score}_{cutoff}.json")

if __name__ == '__main__':
    main()