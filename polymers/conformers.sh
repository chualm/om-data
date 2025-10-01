#!/bin/bash
#SBATCH --job-name=conformer
#SBATCH --output=conformer_%A_%a.out
#SBATCH --constraint=gpu
#SBATCH --gpus=1
#SBATCH --cpus-per-task=32 
#SBATCH --mem=32G
#SBATCH --time=24:00:00  

#SBATCH --array=0-999

idx=$((${SLURM_ARRAY_TASK_ID}+0))

source ~/.bashrc

mamba activate loqi
export PYTHONPATH="./src:$PYTHONPATH"

python conformer_eval.py --smiles_bank "traditional_charges.csv" \
                         --smiles_dir "$HOME/OPEN_25/om-data/omer-files/" \
                         --working_dir "$HOME/OPEN_25/omer/EVALS/output/" \
                         --loqi_path "$SCRATCH/LoQI/" \
                         --n_chunks 1000 \
                         --chunk_idx $idx \
                         --n_samples 5 
