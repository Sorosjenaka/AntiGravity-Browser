import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_hub import DEFAULT_CLI_PATH, run_workflow_cli  # noqa: E402


def _read_multiline_prompt() -> str:
    print("Ketik atau tempel isi prompt custom kamu (akhiri dengan baris berisi 'END' lalu Enter):")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def build_sample_outputs(state: dict) -> list[dict]:
    policy = state.get("policy") or {}
    lang = (policy.get("language") or "en").lower()
    min_w = int(policy.get("min_words") or 7)
    max_w = int(policy.get("max_words") or 9)
    allow_q = bool(policy.get("allow_questions", False))

    if lang.startswith("id"):
        base_samples = [
            ("Glint bikin proses indexing makin ngebut buat builder sekarang", 74, 4),
            ("Update baru Glint ini langsung kerasa manfaatnya di produksi", 65, 3),
            ("Performa Glint makin solid dibanding proyek sejenis minggu ini", 58, 3),
        ]
    else:
        base_samples = [
            ("Glint makes faster indexing immediately useful for builders today", 74, 4),
            ("Glint keeps shipping real speed while others chase hype", 65, 3),
            ("Clean Glint execution shows up straight in query latency", 58, 3),
        ]

    # Adjust sample word counts gracefully if user configured a custom min/max word range
    adjusted = []
    for idx, (text, prob, stars) in enumerate(base_samples, 1):
        words = text.split()
        filler = ["across", "production", "workflows", "right", "now", "with", "consistent", "uptime"]
        fi = 0
        while len(words) < min_w:
            words.append(filler[fi % len(filler)])
            fi += 1
        if len(words) > max_w:
            words = words[:max_w]
        out_text = " ".join(words)
        if allow_q and idx == 3 and not out_text.endswith("?"):
            out_text = out_text + "?"
        adjusted.append(
            {
                "option": idx,
                "text": out_text,
                "word_count": len(words),
                "reply_probability": prob,
                "stars": stars,
                "recommended": idx == 1,
            }
        )
    return adjusted


def print_prompt_and_samples(state: dict):
    pol = state.get("policy") or {}
    source_lbl = "Prompt Custom User" if state.get("source") == "user_custom" else "Prompt Bawaan Repo (reply_prompt.md)"
    print("\n============================================================")
    print(f"Prompt Aktif : {source_lbl}")
    print(
        f"Aturan Logika: language={pol.get('language', 'en')} | "
        f"kata={pol.get('min_words', 7)}-{pol.get('max_words', 9)} | "
        f"wajib_project_short={pol.get('require_project_short', True)} | "
        f"boleh_tanya={pol.get('allow_questions', False)}"
    )
    print("------------------------------------------------------------")
    print(state.get("prompt_text", "").strip())
    print("------------------------------------------------------------")
    print("Contoh Postingan Target (Sampel):")
    print('  "Glint just shipped v2 indexing with 3x faster queries for onchain builders."')
    print("\nSampel Output dari Prompt Ini:")
    print("| Opsi | Balasan Sampel | Kata | Prob | Skor | Rekomendasi |")
    print("|---:|---|---:|---:|---:|---|")
    for s in build_sample_outputs(state):
        rec = "UTAMA" if s["recommended"] else "-"
        print(
            f"| {s['option']} | {s['text']} | {s['word_count']} | {s['reply_probability']}% | {s['stars']}/5 | {rec} |"
        )
    print("============================================================")


def _prompt_policy_args() -> list[str]:
    args: list[str] = []
    lang = input("Bahasa output balasan [en / id / any, Enter = en]: ").strip().lower()
    if lang:
        args.extend(["--language", lang])
    min_w = input("Minimal jumlah kata per balasan [Enter = 7]: ").strip()
    if min_w.isdigit():
        args.extend(["--min-words", min_w])
    max_w = input("Maksimal jumlah kata per balasan [Enter = 9]: ").strip()
    if max_w.isdigit():
        args.extend(["--max-words", max_w])
    allow_q = input("Boleh ada tanda tanya (?) di balasan? [y/N]: ").strip().lower()
    if allow_q in ("y", "yes", "ya"):
        args.append("--allow-questions")
    req_proj = input("Wajib sebut nama pendek project? [Y/n]: ").strip().lower()
    if req_proj in ("n", "no", "tidak"):
        args.append("--no-project-short")
    return args


def _configure_custom_prompt_interactive(cli_path: Path, db_path: Path | None) -> dict:
    print("\nPilih sumber prompt custom kamu:")
    print("  [1] Baca dari file (.md / .txt)")
    print("  [2] Ketik / tempel teks prompt langsung di terminal")
    src_choice = input("Pilih [1/2, Enter = 2]: ").strip() or "2"
    policy_args = _prompt_policy_args()

    if src_choice == "1":
        while True:
            fpath = input("Masukkan path file prompt custom: ").strip().strip('"')
            p = Path(fpath)
            if p.is_file():
                raw = run_workflow_cli(
                    ["set-prompt", "--file", str(p), *policy_args, "--json"],
                    cli_path=cli_path,
                    db_path=db_path,
                )
                return json.loads(raw)
            print(f"File tidak ditemukan: {fpath}")
    else:
        while True:
            txt = _read_multiline_prompt()
            if txt:
                Path("custom_prompt.md").write_text(txt + "\n", encoding="utf-8")
                raw = run_workflow_cli(
                    ["set-prompt", "--file", "custom_prompt.md", *policy_args, "--json"],
                    cli_path=cli_path,
                    db_path=db_path,
                )
                return json.loads(raw)
            print("Teks prompt tidak boleh kosong.")


def run_prompt_wizard(
    cli_path: Path = DEFAULT_CLI_PATH,
    db_path: Path | None = None,
    mode: str = "ask",
    prompt_file: str | None = None,
    prompt_text: str | None = None,
    non_interactive: bool = False,
) -> dict:
    if prompt_file:
        raw = run_workflow_cli(
            ["set-prompt", "--file", prompt_file, "--json"],
            cli_path=cli_path,
            db_path=db_path,
        )
        state = json.loads(raw)
    elif prompt_text:
        Path("custom_prompt.md").write_text(prompt_text.strip() + "\n", encoding="utf-8")
        raw = run_workflow_cli(
            ["set-prompt", "--file", "custom_prompt.md", "--json"],
            cli_path=cli_path,
            db_path=db_path,
        )
        state = json.loads(raw)
    elif mode == "default":
        raw = run_workflow_cli(
            ["set-prompt", "--default", "--json"],
            cli_path=cli_path,
            db_path=db_path,
        )
        state = json.loads(raw)
    elif mode == "custom":
        if non_interactive or not sys.stdin.isatty():
            raise ValueError("Mode custom non-interactive membutuhkan --prompt-file atau --prompt-text.")
        state = _configure_custom_prompt_interactive(cli_path, db_path)
    else:
        if non_interactive or not sys.stdin.isatty():
            state = json.loads(run_workflow_cli(["show-prompt", "--json"], cli_path=cli_path, db_path=db_path))
        else:
            print("\n=== Pilih Prompt yang Mau Dipakai ===")
            print("  [1] Pakai prompt bawaan di dalam repo (reply_prompt.md)")
            print("  [2] Pakai prompt custom buatan kamu sendiri")
            choice = input("Pilih prompt [1/2, Enter = 1]: ").strip() or "1"
            if choice == "2":
                state = _configure_custom_prompt_interactive(cli_path, db_path)
            else:
                state = json.loads(
                    run_workflow_cli(["set-prompt", "--default", "--json"], cli_path=cli_path, db_path=db_path)
                )

    print_prompt_and_samples(state)
    if non_interactive or not sys.stdin.isatty():
        return state

    while True:
        print("\nApakah output sampel dari prompt ini sudah cocok dan sesuai?")
        print("  [1] Ya, sudah cocok & sesuai — lanjutkan")
        print("  [2] Tambahkan penegasan untuk memperjelas logika / aturan baru")
        print("  [3] Perbaiki / ganti prompt custom atau ubah batasan kata/bahasa")
        print("  [4] Reset ke prompt bawaan repo (reply_prompt.md)")
        ans = input("Pilih [1-4, Enter = 1]: ").strip() or "1"
        if ans == "1":
            print("Sip! Konfigurasi prompt dan logika balasan sudah dikunci.")
            return state
        if ans == "2":
            rule = input("Tulis penegasan logika / aturan tambahan yang ingin ditegaskan: ").strip()
            if rule:
                state = json.loads(
                    run_workflow_cli(
                        ["set-prompt", "--append-rule", rule, "--json"],
                        cli_path=cli_path,
                        db_path=db_path,
                    )
                )
                print_prompt_and_samples(state)
            else:
                print("Penegasan tidak boleh kosong.")
        elif ans == "3":
            state = _configure_custom_prompt_interactive(cli_path, db_path)
            print_prompt_and_samples(state)
        elif ans == "4":
            state = json.loads(
                run_workflow_cli(["set-prompt", "--default", "--json"], cli_path=cli_path, db_path=db_path)
            )
            print_prompt_and_samples(state)
        else:
            print("Pilihan tidak valid. Masukkan angka 1-4.")


def main():
    parser = argparse.ArgumentParser(
        description="Interactive prompt chooser (custom vs repo default), sample previewer, and logic clarification wizard."
    )
    parser.add_argument("--cli-path", default=str(DEFAULT_CLI_PATH))
    parser.add_argument("--db", default=None)
    parser.add_argument("--mode", default="ask", choices=["ask", "default", "custom"])
    parser.add_argument("--prompt-file", default=None)
    parser.add_argument("--prompt-text", default=None)
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()

    run_prompt_wizard(
        cli_path=Path(args.cli_path),
        db_path=Path(args.db) if args.db else None,
        mode=args.mode,
        prompt_file=args.prompt_file,
        prompt_text=args.prompt_text,
        non_interactive=args.non_interactive,
    )


if __name__ == "__main__":
    main()
