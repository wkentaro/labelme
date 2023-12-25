import gdown

from .segment_anything_model import SegmentAnythingModel


class SegmentAnythingModelVitB(SegmentAnythingModel):
    name = "SegmentAnything (speed)"

    def __init__(self):
        super().__init__(
            encoder_path=gdown.cached_download(
                url="https://github.com/wkentaro/labelme/releases/download/sam-20230416/sam_vit_b_01ec64.quantized.encoder.onnx",  # NOQA
                md5="80fd8d0ab6c6ae8cb7b3bd5f368a752c",
            ),
            decoder_path=gdown.cached_download(
                url="https://github.com/wkentaro/labelme/releases/download/sam-20230416/sam_vit_b_01ec64.quantized.decoder.onnx",  # NOQA
                md5="4253558be238c15fc265a7a876aaec82",
            ),
        )


class SegmentAnythingModelVitL(SegmentAnythingModel):
    name = "SegmentAnything (balanced)"

    def __init__(self):
        super().__init__(
            encoder_path=gdown.cached_download(
                url="https://github.com/wkentaro/labelme/releases/download/sam-20230416/sam_vit_l_0b3195.quantized.encoder.onnx",  # NOQA
                md5="080004dc9992724d360a49399d1ee24b",
            ),
            decoder_path=gdown.cached_download(
                url="https://github.com/wkentaro/labelme/releases/download/sam-20230416/sam_vit_l_0b3195.quantized.decoder.onnx",  # NOQA
                md5="851b7faac91e8e23940ee1294231d5c7",
            ),
        )


class SegmentAnythingModelVitH(SegmentAnythingModel):
    name = "SegmentAnything (accuracy)"

    def __init__(self):
        super().__init__(
            encoder_path=gdown.cached_download(
                url="https://github.com/wkentaro/labelme/releases/download/sam-20230416/sam_vit_h_4b8939.quantized.encoder.onnx",  # NOQA
                md5="958b5710d25b198d765fb6b94798f49e",
            ),
            decoder_path=gdown.cached_download(
                url="https://github.com/wkentaro/labelme/releases/download/sam-20230416/sam_vit_h_4b8939.quantized.decoder.onnx",  # NOQA
                md5="a997a408347aa081b17a3ffff9f42a80",
            ),
        )


MODELS = [
    SegmentAnythingModelVitL,
    SegmentAnythingModelVitB,
    SegmentAnythingModelVitH,
]
