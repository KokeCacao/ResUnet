import random
import numpy as np


# def get_square(img, pos):
#     """Extract a left or a right square from ndarray shape : (H, W, C))"""
#     h = img.shape[0]
#     if pos == 0:
#         return img[:, :h]
#     else:
#         return img[:, -h:]

# def split_img_into_squares(img):
#     return get_square(img, 0), get_square(img, 1)

def hwc_to_chw(img):
    return np.transpose(img, axes=[2, 0, 1])

# pilimg = image input
# scale = resize to what percent
# final_height =
def resize_and_crop(pilimg, scale=96, final_height=None):
    w = pilimg.size[0]
    h = pilimg.size[1]
    newW = int(scale)
    newH = int(scale)

    if not final_height:
        diff = 0
    else:
        diff = newH - final_height

    img = pilimg.resize((newW, newH))
    # cropped = img.crop( ( left, top, right, bottom ) )
    img = img.crop((0, diff // 2, newW, newH - diff // 2))
    return np.array(img, dtype=np.float32)

def batch(iterable, batch_size):
    """Yields lists by batch"""
    b = []
    for i, t in enumerate(iterable):
        b.append(t)
        if (i + 1) % batch_size == 0:
            yield b
            b = []

    if len(b) > 0:
        yield b

def split_train_val(dataset, val_percent=0.05):
    dataset = list(dataset)
    length = len(dataset)
    n = int(length * val_percent)
    random.shuffle(dataset)
    return {'train': dataset[:-n], 'val': dataset[-n:]}


def normalize(x):
    return x / 255

# def merge_masks(img1, img2, full_w):
#     h = img1.shape[0]
#
#     new = np.zeros((h, full_w), np.float32)
#     new[:, :full_w // 2 + 1] = img1[:, :full_w // 2 + 1]
#     new[:, full_w // 2 + 1:] = img2[:, -(full_w // 2 - 1):]
#
#     return new

