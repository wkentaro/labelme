from labelme import app
import os
import shutil
from labelme.logger import logger
import json

class MainWindow(app.MainWindow):
    queue_name: str = "preprocessed"
    fail_stage: str = "rescan"
    pass_stage: str = "initial_labelled"

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

    def load_queue(self):
        self.data_path = os.path.abspath("data")
        if os.path.exists(self.data_path):
            shutil.rmtree(self.data_path)

        os.makedirs(self.data_path)

        models = self.load_models_queue(self.queue_name)
        print("Models")
        print(models)
        self.aws_api.configure_buckets("danville-labelling", "danville-labelling")

        for model in models:
            folder = model["folder"].strip("/")
            image_key = "{}.jpg".format(folder)
            label_key = "{}.json".format(folder)
            self.aws_api.read_from_s3(image_key, os.path.join(self.data_path, image_key))
            self.aws_api.read_from_s3(label_key, os.path.join(self.data_path, label_key))

        self.importDirImages(self.data_path)

    def save_labels(self, filename, shapes, flags):
        label_file = os.path.abspath(os.path.join(
            self.data_path,
            "{}.json".format(os.path.splitext(os.path.split(filename)[-1])[0])
        ))

        folder = os.path.splitext(os.path.split(filename)[-1])[0].strip("/")

        aws_fp = "completed_{}.json".format(os.path.splitext(os.path.split(filename)[-1])[0])

        if flags["Bad Raster"]:
            self.manual_api.setStage(folder, self.fail_stage)
            logger.info("Scan {} Failed, sent to rescan".format(folder))
            return

        with open(label_file) as f:
            data = json.load(f)

        if 'regions' in data and data["regions"] is not None:
            data['regions'] += shapes
        else:
            data["regions"] = shapes
        
        data['initial_name'] = self.manual_api.username

        with open(label_file, 'w', encoding='utf-8') as updated_fd:
            json.dump(data, updated_fd, ensure_ascii=False, indent=4)
        
        self.aws_api.output_s3(label_file, aws_fp)
        self.manual_api.setStage(folder, self.pass_stage)
        logger.info("Pushed {} to s3 bucket".format(label_file))
