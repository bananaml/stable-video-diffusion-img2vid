FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

WORKDIR /

# Install git
RUN apt-get update && apt-get install -y git git-lfs 

# Download generative-models repo
RUN git clone https://github.com/Stability-AI/generative-models.git

# Download checkpoint
RUN git lfs install
RUN git clone https://huggingface.co/stabilityai/stable-video-diffusion-img2vid checkpoints

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get install -y libgl1\
    libgl1-mesa-glx \ 
    libglib2.0-0

# Install python packages.
RUN pip3 install --upgrade pip
RUN pip3 install -r generative-models/requirements/pt2.txt
RUN pip3 install ./generative-models
RUN pip3 install potassium requests

ADD . .

EXPOSE 8000

CMD python3 -u app.py
