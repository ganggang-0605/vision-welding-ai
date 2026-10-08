"""전처리: Retinexformer(조도), OpenCV(시점 보정), SIHR(반사 제거)"""


def preprocess(image):
    """노이즈·오염·스크래치 제거. (보정된 이미지, 보정 강도 0~1) 반환"""
    # TODO: Retinexformer / SIHR 연동, OpenCV 원근 보정
    return image, 0.0
