import base64
import io

import numpy as np
import PIL.ExifTags
import PIL.Image
import PIL.ImageOps
import cv2


def img_data_to_pil(img_data):
    f = io.BytesIO()
    f.write(img_data)
    img_pil = PIL.Image.open(f)
    return img_pil


def img_data_to_arr(img_data):
    img_pil = img_data_to_pil(img_data)
    img_arr = np.array(img_pil)
    return img_arr


def img_b64_to_arr(img_b64):
    img_data = base64.b64decode(img_b64)
    img_arr = img_data_to_arr(img_data)
    return img_arr


def img_pil_to_data(img_pil):
    f = io.BytesIO()
    img_pil.save(f, format="PNG")
    return f.getvalue()


def img_arr_to_b64(img_arr):
    img_pil = PIL.Image.fromarray(img_arr)
    f = io.BytesIO()
    img_pil.save(f, format="PNG")
    img_bin = f.getvalue()
    if hasattr(base64, "encodebytes"):
        img_b64 = base64.encodebytes(img_bin)
    else:
        img_b64 = base64.encodestring(img_bin)
    return img_b64


def img_data_to_png_data(img_data):
    with io.BytesIO() as f:
        f.write(img_data)
        img = PIL.Image.open(f)
        with io.BytesIO() as f:
            img.save(f, "PNG")
            f.seek(0)
            return f.read()


def normalize_image(img):
    if not isinstance(img, np.ndarray):
        np_img = np.array(img)
    else:
        np_img = img
    if img.dtype == "uint8":
        np_img = (cv2.normalize(
            np_img,
            None,
            alpha=0,
            beta=1,
            norm_type=cv2.NORM_MINMAX,
            dtype=cv2.CV_32F) * 255).astype(np.uint8)
    else:
        np_img = (cv2.normalize(
            np_img,
            None,
            alpha=0,
            beta=1,
            norm_type=cv2.NORM_MINMAX,
            dtype=cv2.CV_32F) * 2**16 - 1).astype(np.uint16)
    # img_t = PIL.Image.fromarray(np_img.astype("uint8"),mode="L")
    return np_img


def apply_exif_orientation(image):
    try:
        exif = image._getexif()
    except AttributeError:
        exif = None

    if exif is None:
        return image

    exif = {
        PIL.ExifTags.TAGS[k]: v
        for k, v in exif.items()
        if k in PIL.ExifTags.TAGS
    }

    orientation = exif.get("Orientation", None)

    if orientation == 1:
        # do nothing
        return image
    elif orientation == 2:
        # left-to-right mirror
        return PIL.ImageOps.mirror(image)
    elif orientation == 3:
        # rotate 180
        return image.transpose(PIL.Image.ROTATE_180)
    elif orientation == 4:
        # top-to-bottom mirror
        return PIL.ImageOps.flip(image)
    elif orientation == 5:
        # top-to-left mirror
        return PIL.ImageOps.mirror(image.transpose(PIL.Image.ROTATE_270))
    elif orientation == 6:
        # rotate 270
        return image.transpose(PIL.Image.ROTATE_270)
    elif orientation == 7:
        # top-to-right mirror
        return PIL.ImageOps.mirror(image.transpose(PIL.Image.ROTATE_90))
    elif orientation == 8:
        # rotate 90
        return image.transpose(PIL.Image.ROTATE_90)
    else:
        return image

class InferenceHandler(object):
    def __init__(self, img, crop_shape, overlaps=[20, 20]) -> None:

        assert overlaps[0] % 2 == 0, "Overlaps y-dim must be divisible by 2"
        assert overlaps[1] % 2 == 0, "Overlaps x-dim must be divisible by 2"
        if crop_shape is not None and len(crop_shape)==4:
            self.crop_shape = crop_shape[2:]
        else:
            self.crop_shape = crop_shape
        self.overlaps = overlaps
        self.img_shape = img.shape
        zero_img = self._get_zero_img()
        self.pred_stack = np.zeros((self.crop_shape[0], self.crop_shape[1], (self.n_splits_x + 1) * (self.n_splits_y + 1))) 
        zero_img[:self.img_shape[0], :self.img_shape[1]] = img
        self.padded_img = zero_img
        del zero_img
        self.joined_pred = np.zeros(self.padded_img.shape)

    def __len__(self):
        """retuns the total number of patches"""
        return (self.n_splits_x + 1) * (self.n_splits_y + 1)


    def _get_zero_img(self):
        self.n_splits_y = self.img_shape[0] // self.crop_shape[0]
        self.n_splits_x = self.img_shape[1] // self.crop_shape[1]
        return np.zeros([(self.n_splits_y + 1) * self.crop_shape[0], (self.n_splits_x + 1) * self.crop_shape[1]])

    def get_crop_stack(self):
        self.img_stack = np.zeros(((self.n_splits_x + 1) * (self.n_splits_y + 1), self.crop_shape[0], self.crop_shape[1]))

        for i in range(self.n_splits_y + 1):
            increment_y = i * (self.crop_shape[0] - self.overlaps[0])
            for j in range(self.n_splits_x + 1):
                increment_x = j * (self.crop_shape[1] - self.overlaps[1])
                self.img_stack[(j + i * (self.n_splits_x + 1)), :, :] = self.padded_img[increment_y:increment_y + self.crop_shape[0], increment_x:increment_x + self.crop_shape[1]]
        return self.img_stack

    def set_stack_element(self, prediction, index):
        self.pred_stack[:, :, index] = prediction

    def join_pred(self):

        half_overlaps = [int(i / 2) for i in self.overlaps]
        for i in range(len(self)):

            # initialize bool values for cropping conditions
            current_col = i % (self.n_splits_x + 1)
            current_row = i // (self.n_splits_x + 1)
            slice_y = slice(half_overlaps[0], - half_overlaps[0])
            slice_x = slice(half_overlaps[1], - half_overlaps[1])
            y_span = self.crop_shape[0] - self.overlaps[0]
            x_span = self.crop_shape[1] - self.overlaps[1]

            # crop only right side if the first element of a row is written
            if current_col == 0:
                slice_x = slice(0, -half_overlaps[1])
                x_span = self.crop_shape[1] - half_overlaps[1]

            # crop only left side if the last element of a row is written
            elif current_col == self.n_splits_x:
                slice_x = slice(half_overlaps[1], self.crop_shape[1])
                x_span = self.crop_shape[1] - half_overlaps[1]

            # crop top only if it's not the first row
            if current_row == 0:
                slice_y = slice(0, -half_overlaps[0])
                y_span = self.crop_shape[0] - half_overlaps[0]
            # crop bottom only if it's not the last row
            elif current_row == self.n_splits_y:
                slice_y = slice(half_overlaps[0], self.crop_shape[0])
                y_span = self.crop_shape[0] - half_overlaps[0]

            # writing back the crop to the joined prediction

            if current_row >= 2:
                offset_y = (current_row - 1) * half_overlaps[0]
            else:
                offset_y = 0

            slice_joined_y = slice(current_row * (self.crop_shape[0] - half_overlaps[0]) - offset_y, current_row * (self.crop_shape[0] - half_overlaps[0]) + y_span - offset_y)
            slice_joined_x = slice(current_col * (self.crop_shape[1] - half_overlaps[1]), current_col * (self.crop_shape[1] - half_overlaps[1]) + x_span)
            self.joined_pred[slice_joined_y, slice_joined_x] = self.pred_stack[slice_y, slice_x, i]

        return self.joined_pred[:self.img_shape[0], :self.img_shape[1]]

def polygonfit(image, precision=0.0007, closeKernel=[5, 5], dilKernel=[3, 3]):
    """
    precision as measure of how fine to approximate the shape by a polygon, a lower value for better approximation by more points
    closeKernel, dilKernel: kernel size for rectangular kernel, need to be adjusted depending on preprocessing
    """
    closeKernel=cv2.getStructuringElement(cv2.MORPH_RECT,(closeKernel[0],closeKernel[1]))
    dilKernel=cv2.getStructuringElement(cv2.MORPH_RECT,(dilKernel[0],dilKernel[1]))
    #Obsolete for multi-instance segmentation
    # if image.shape[2]>1:
    #     image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    image=(image*255).astype(np.uint8)
    image=cv2.GaussianBlur(image,(5,5),0)
    _,binImg = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    #_,binImg= cv2.threshold(image, 190, 255, cv2.THRESH_BINARY)
    #binImg=cv2.morphologyEx(binImg,cv2.MORPH_CLOSE,closeKernel)
    #binImg=cv2.morphologyEx(binImg,cv2.MORPH_ERODE,dilKernel)
    #binImg=cv2.morphologyEx(binImg,cv2.MORPH_DILATE,dilKernel)
    edge = cv2.Canny(binImg, 100, 200)
    (cnts, _) = cv2.findContours(edge.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    approx=[]
    for c in cnts:
        epsilon = precision * cv2.arcLength(c, True)
        approx.append(cv2.approxPolyDP(c, epsilon, True))
    return approx