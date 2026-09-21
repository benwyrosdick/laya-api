"""Download Laya checkpoints into the Hugging Face hub cache."""

BUNDLE = "convaiinnovations/laya"


def download() -> str:
    from huggingface_hub import snapshot_download

    return snapshot_download(BUNDLE)


def main() -> None:
    path = download()
    print(f"Cached {BUNDLE} at {path}")


if __name__ == "__main__":
    main()
