from hitrax import calc


def test_calc_prints_carry(capsys):
    calc.main(["100", "28"])
    out = capsys.readouterr().out
    assert "dead center" in out
    assert "Fly ball, fair" in out
    assert "Carry" in out


def test_calc_takes_negative_spray(capsys):
    calc.main(["95", "20", "-50"])
    out = capsys.readouterr().out
    assert "50° toward left field" in out
    assert "foul" in out
