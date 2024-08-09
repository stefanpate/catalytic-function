from src.cross_validation import BatchGridSearch, BatchScript, HyperHyperParams

dataset_name = 'sprhea'
toc = 'v3_folded_pt_ns' # Name of file with protein id | features/labels | sequence
n_splits = 5
seed = 1234
allocation = 'b1039'
partition = 'b1039'
mem = '12G' # 12G
time = '38' # Hours 36
fit_script = 'two_channel_fit.py'
neg_multiple = 1
split_strategy = 'homology'
split_sim_threshold = 0.8
embed_type = 'esm'
res_dir = "/projects/p30041/spn1560/hiec/artifacts/model_evals/gnn"

# Configurtion stuff
hhps = HyperHyperParams(
    dataset_name=dataset_name,
    toc=toc,
    neg_multiple=neg_multiple,
    n_splits=n_splits,
    split_strategy=split_strategy,
    embed_type=embed_type,
    seed=seed,
    split_sim_threshold=split_sim_threshold,
)

# Create grid search object
gs = BatchGridSearch(
    hhps=hhps,
    res_dir=res_dir,
)

# Choose hyperparameters for grid search
hps = {
    'n_epochs':[25], # int
    'pred_head':['dot_sig'], # 'binary' | 'dot_sig'
    'message_passing':['bondwise'], # 'bondwise' | 'bondwise_dict' | None
    'agg':['last', 'mean'], # 'mean' | 'last' | 'attention' | None
    'd_h_encoder':[300], # int
    'model':['mpnn_dim_red'], # 'mpnn' | 'mpnn_dim_red' | 'ffn' | 'linear'
    'featurizer':['rxn_rc'], # 'rxn_simple' | 'rxn_rc' | 'mfp'
    'encoder_depth':[5, 6], # int | None
}

# Slurm stuff
batch_script = BatchScript(
    allocation=allocation,
    partition=partition,
    mem=mem,
    time=time,
    script=fit_script
)

# Run grid search
gs.run(
    hps=hps,
    batch_script=batch_script,
)