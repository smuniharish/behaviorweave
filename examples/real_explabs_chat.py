"""Opt-in live LangChain model smoke test; never put credentials in this file."""

from common import create_explabs_model


def main() -> None:
    response = create_explabs_model().invoke("Return exactly: BehaviorWeave real-model smoke test")
    print(response.content)


if __name__ == "__main__":
    main()
