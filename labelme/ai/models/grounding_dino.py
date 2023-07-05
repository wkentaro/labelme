import numpy as np

from PIL import Image
from git import Repo

import os
import sys
from gdown.cached_download import cache_root
from pathlib import Path
import wget
import importlib

HF_LINK = "https://huggingface.co/ShilongLiu/GroundingDINO/resolve/main/groundingdino_swint_ogc.pth"
REPO_LINK = "https://github.com/IDEA-Research/GroundingDINO.git"
CONFIG_PATH = None
MODEL_PATH = None

repo_path = Path(cache_root)/"GroundingDINO"
if not os.path.isdir(str(repo_path)) :
    Repo.clone_from(REPO_LINK, str(repo_path))
CONFIG_PATH = str(Path(repo_path)/"groundingdino/config/GroundingDINO_SwinT_OGC.py")

sys.path.append(str(repo_path))
import groundingdino.datasets.transforms as T
from groundingdino.util.inference import load_model, predict
# self.additional_modules["T"] = importlib.import_module("groundingdino.datasets.transforms")
# self.additional_modules["load_model"] = importlib.import_module("groundingdino.datasets.load_model")
# self.additional_modules["predict"] = importlib.import_module("groundingdino.datasets.predict")


class GroundingDINOModel:
    
    def __init__(self):

        self.model = None
        self.box_thr = 0.35
        self.text_thr = 0.25
        self.download_model_files()
        self.additional_modules = {}
        
    def download_model_files (self) :
        
        model_path = Path(cache_root)/"groundingdino_swint_ogc.pth"
        if not os.path.isfile(str(model_path)) :
            wget.download(HF_LINK, out=str(model_path))
        global MODEL_PATH
        MODEL_PATH = str(model_path)

        print("GroundingDINO download done!")

    def load_model (self, model_path) :
        
        self.model = load_model(CONFIG_PATH, MODEL_PATH)
    
    def predict (self, prompt, image) :
        
        image_source, image = self.load_image(image)
        
        boxes, logits, phrases = predict(
            model=self.model,
            image=image,
            caption=prompt,
            box_threshold=self.box_thr,
            text_threshold=self.text_thr,
            device="cpu"
        )

        return boxes.to("cpu").numpy()
    
    
    def load_image(self, image_source) :
        transform = T.Compose(
            [
                T.RandomResize([800], max_size=1333),
                T.ToTensor(),
                T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        image = np.asarray(image_source[:, :, :3])
        image_transformed, _ = transform(Image.fromarray(image_source[:, :, :3]), None)
        return image, image_transformed
