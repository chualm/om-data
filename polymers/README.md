# Revised Instructions
Disclaimer: the following worked for NERSC.


## Step 1: Clone the repo
```bash
git clone https://github.com/isayevlab/LoQI.git
cd LoQI
```
## Step 2: Environment
```bash
conda create -n loqi python=3.10 -y
conda activate loqi
```

```bash
pip install torch==2.7.0
pip install torch-scatter torch-sparse torch-cluster torch-spline-conv   \
 -f https://data.pyg.org/whl/torch-$(python -c "import torch; print(torch.__version__.split('+')[0])").html

pip install -e .
pip install -r requirements.txt

# for workflow
pip install ase
conda install conda-forge::openbabel
```

## Step 3: Download LoQI files
Download both from [this link] (https://drive.google.com/drive/folders/1PvSrep7_qIjTSslzXD3KUYEJ2Qr2lgDD)

Make sure you are still in `LoQI/`

```bash
mkdir LoQI_data
```

Place `loqi.ckpt` and `chembl3d_stereo` in `LoQI_data/`

In `LoQI/scripts/conf/loqi/loqi.yaml`, set the right path:
```python
# .....
data:
  dataset_root: "$PATH_TO_LOQI/LoQI_data/chembl3d_stereo"
# .....

```

## Step 4: Running

Edit paths accordingly
```
sbatch conformers.sh
```






