from vw_shared.validate import main


def test_examples_pass_all_checks():
    """python -m vw_shared.validate 와 같음: 예시·스키마·단계 사이 규칙·시드 DB·예시 흐름"""
    assert main() == 0
