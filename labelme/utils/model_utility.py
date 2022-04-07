def get_fitted_shape(img_shape, divisor=64):
    y_dim = np.ceil(img_shape[0] / divisor)
    x_dim = np.ceil(img_shape[1] / divisor)
    return [int(y_dim * divisor), int(x_dim * divisor)]


def adjust_model_input(model_path, input_shape):
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    if input_shape is None:
        return tf.keras.models.load_model(model_path, compile=False)
    fitted_shape = get_fitted_shape(input_shape[2:], 64)
    input_layer_shape = (fitted_shape[0], fitted_shape[1], 1)
    os.chdir(model_path.parent)
    model = tf.keras.models.load_model(model_path, compile=False)
    model.layers.pop(0)
    new_input = tf.keras.layers.Input(shape=input_layer_shape, name='input')
    new_outputs = model(new_input)
    model_output_names = [output.name for output in model._output_layers]
    model = tf.keras.models.Model(new_input, new_outputs)
    model.output_names = model_output_names
    return model


def predict_default(tensor: np.ndarray, model):
    return model.predict_on_batch(tensor)

# preperation


def transform_image_to_framework(framework=None, image=None, max_value=4095, shift=0, channels=1):
    if framework == "ov":
        tensor = np.zeros([1, channels, image.shape[0], image.shape[1]]).astype(np.float32)
    elif framework == "tf":
        tensor = np.zeros([1, image.shape[0], image.shape[1], 1]).astype(np.float32)
    elif framework == "tflite":
        tensor = np.zeros([1, image.shape[0], image.shape[1], channels]).astype(np.float32)

    if framework == "ov":
        tensor[0, 0, :, :] = (image / max_value)
    elif framework == "tf":
        tensor[0, :image.shape[0], :image.shape[1], 0] = image / max_value
    elif framework == "tflite":
        tensor[0, :, :, 0] = image / max_value
    return tensor


def invert_transform(framework=None, tensor=None, img_shape=None, max_value=255, channels=1):
    if framework == "ov":
        # tensor = tensor.buffer
        image = ((tensor[:, 0]).reshape([img_shape[0], img_shape[1]])) * max_value
    elif framework == "tf":
        image = tensor[0].reshape([img_shape[0], img_shape[1]]) * max_value
    if max_value == 255:
        image = image.astype(np.uint8)
    elif max_value > 255:
        image = image.astype(np.uint16)
    return image