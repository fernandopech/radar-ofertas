import os

from app import config


def test_env_preenchido_vence_variavel_de_ambiente(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_CANAIS=a,b,c\nSUPABASE_KEY=\n")
    monkeypatch.setattr(config, "ARQUIVO_ENV", env)
    monkeypatch.setenv("TELEGRAM_CANAIS", "a")         # secret antigo do Codespaces
    monkeypatch.setenv("SUPABASE_KEY", "sb_secret_x")  # vazio no .env não pode apagar
    config._carregar_env()
    assert os.environ["TELEGRAM_CANAIS"] == "a,b,c"
    assert os.environ["SUPABASE_KEY"] == "sb_secret_x"
