from labelme import app
import os
import shutil

class MainWindow(app.MainWindow):
    queue_name: str = "qc"
    fail_stage: str = "failed"
    pass_stage: str = "passed"

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

    def load_queue(self):
        self.data_path = os.path.abspath("data")
        if os.path.exists(self.data_path):
            shutil.rmtree(self.data_path)

        os.makedirs(self.data_path)

        models = self.load_models_queue(self.queue_name)
        self.aws_api.configure_buckets("lidar-results", "lidar-results")

        for model in models:
            folder = model["folder"].strip("/")
            image_key = folder + "/" + "d_unchecked.jpg"
            self.aws_api.read_from_s3(
                image_key,
                os.path.join(self.data_path, folder + "_d_unchecked.jpg")
            )

        self.importDirImages(self.data_path)

    def save_labels(self, filename, shapes, flags):
        folder = os.path.split(filename)[-1].split("_")[0]
        failures = ""

        if flags["Pass"]:
            self.manual_api.setStage(folder, self.pass_stage)
            return
        
        gen = (flag for flag in flags if flag != "Pass" and flags[flag])
        for flag in gen:
            failures += "_" + flag if failures else flag

        if failures:
            self.manual_api.setFailures(folder, failures)
            self.manual_api.setStage(folder, self.fail_stage)
