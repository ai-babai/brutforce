"""Isolated B variant: bound the BGR OCR input to 1280 pixels longest side.

This changes image resampling and may change OCR/rank quality. It is a distinct
experimental configuration, not a drop-in output-preserving acceleration.
"""
import cv2
import softgate_server


OriginalPipeline = softgate_server.Pipeline


class OCR1280Pipeline(OriginalPipeline):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        original_predict = self.ocr.predict

        def bounded_predict(image):
            height, width = image.shape[:2]
            longest = max(height, width)
            if longest > 1280:
                scale = 1280 / longest
                image = cv2.resize(image,
                    (max(1, round(width*scale)), max(1, round(height*scale))),
                    interpolation=cv2.INTER_AREA)
            return original_predict(image)

        self.ocr.predict = bounded_predict


softgate_server.Pipeline = OCR1280Pipeline

if __name__ == '__main__':
    softgate_server.main()
