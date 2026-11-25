#!/bin/sh
# ktau's receiver with Whisper on a GPU (#6): server/receiver-gpu.sh <gpu> [receiver.py options]
# <gpu> is nvidia-smi's index. CTranslate2 needs cuBLAS and cuDNN on the library path; they come as wheels.
# With the LLM on the same host (the z170: llama.cpp over both cards, about 1 GB left on the smaller one),
# small.en fits and medium.en does not.
# A host without the Zephyr tree needs liblc3 and its Python binding copied over: LIBLC3 and LC3_PY (tools/lc3dec.py).
set -e
cd "$(dirname "$0")/.."
gpu=$1; shift
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES="$gpu"
exec uv run -q --with faster-whisper --with numpy --with nvidia-cublas-cu12 --with 'nvidia-cudnn-cu12>=9,<10' sh -c '
  export LD_LIBRARY_PATH=$(python -c "import nvidia.cublas.lib as a, nvidia.cudnn.lib as b; print(list(a.__path__)[0] + chr(58) + list(b.__path__)[0])")
  exec python -I server/receiver.py --device cuda --model small.en "$@"' receiver "$@"
