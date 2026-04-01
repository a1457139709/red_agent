from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from cli.ui import get_presenter


step_counter = 0


def reset_steps() -> None:
    global step_counter
    step_counter = 0


def log_step(text: AIMessage | ToolMessage, tool_calls: list) -> None:
    global step_counter
    step_counter += 1

    presenter = get_presenter()
    presenter.show_step_start(step_counter)

    if text.content:
        presenter.show_thinking(str(text.content))

    for call in tool_calls:
        presenter.show_tool_call(call["name"], call["args"])


class ColoredOutput:
    @classmethod
    def print_step(cls, step_num: int, total_steps: int | None = None) -> None:
        get_presenter().show_step_start(step_num, total_steps)

    @classmethod
    def print_tool_call(cls, tool_name: str, args: dict) -> None:
        get_presenter().show_tool_call(tool_name, args)

    @classmethod
    def print_observation(cls, observation: str, truncate: int | None = None) -> None:
        truncate_chars = truncate if truncate is not None else 600
        get_presenter().show_observation(observation, truncate_chars=truncate_chars)

    @classmethod
    def print_final_answer(cls, answer: str) -> None:
        get_presenter().show_final_answer(answer)

    @classmethod
    def print_error(cls, error_msg: str) -> None:
        get_presenter().show_error(error_msg)

    @classmethod
    def print_info(cls, info_msg: str) -> None:
        get_presenter().show_info(info_msg)

    @classmethod
    def print_thinking(cls, thought: str) -> None:
        get_presenter().show_thinking(thought)

    @classmethod
    def print_divider(cls, char: str = '-', length: int = 50, color=None) -> None:
        get_presenter().show_info(char * length)

    @classmethod
    def print_success(cls, msg: str) -> None:
        get_presenter().show_success(msg)

    @classmethod
    def print_header(cls, title: str) -> None:
        get_presenter().show_header(title)

    @classmethod
    def clear_screen(cls) -> None:
        get_presenter().clear_screen()
