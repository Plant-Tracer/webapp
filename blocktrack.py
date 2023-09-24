# Steve gets to finish this.

from PIL import Image


def blocktrack(context, img):
    width, height = img.size
    first5 = "".join([("(%02x%02x%02x) " % img.getpixel((x, 0)))
                     for x in range(0, 5)])
    return {'width': width, 'height': height, 'first5 pixels': first5}
