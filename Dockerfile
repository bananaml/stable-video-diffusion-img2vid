FROM pytorch/pytorch:2.1.1-cuda12.1-cudnn8-runtime

WORKDIR /

# Install git
RUN apt-get update && apt-get install -y git git-lfs

# Download generative-models repo
RUN git clone github.com:Stability-AI/generative-models.git

# Download checkpoint
RUN git lfs install
RUN git clone https://huggingface.co/stabilityai/stable-video-diffusion-img2vid
RUN mv stable-video-diffusion-img2vid checkpoints

# Install python packages.
RUN pip3 install --upgrade pip
ADD requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Add your model weight files 
# (in this case we have a python script)
ADD download.py .
RUN python3 download.py

ADD . .

EXPOSE 8000

CMD python3 -u app.py
