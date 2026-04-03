"""Minimal local smoke tests for the prd_skill service."""

from fastapi.testclient import TestClient

from app import app


def main() -> None:
    """中文说明：运行 interactive v2 与兼容接口的基础冒烟验证。

    输入：无。
    输出：将关键用例结果打印到标准输出。
    关键逻辑：覆盖 interactive 多轮收敛、draft/final 双档、reverse 忽略 quality 与异常路径。
    """

    client = TestClient(app)

    print("CASE: /session/start")
    start_resp = client.post(
        "/session/start",
        json={"mode": "interactive", "input_text": "想做一个帮助运营快速创建活动页的工具"},
    )
    start_body = start_resp.json()
    print(start_resp.status_code)
    print(
        {
            "session_id": start_body["session_id"],
            "turn_count": start_body["turn_count"],
            "status": start_body["status"],
            "can_generate_draft": start_body["can_generate_draft"],
            "can_generate_final": start_body["can_generate_final"],
            "open_questions_count": len(start_body["open_questions"]),
            "next_prompt": start_body["next_prompt"],
        }
    )

    print("\nCASE: /session/continue")
    continue_resp = client.post(
        "/session/continue",
        json={
            "session_id": start_body["session_id"],
            "input_text": (
                "goal: 提升活动创建效率\n"
                "users: 运营, 市场\n"
                "scenarios: 快速创建活动页, 复用模板\n"
                "core_functions: 模板配置, 页面发布\n"
                "conversion_path: 进入后台, 创建活动, 发布上线\n"
                "platform: Web 后台\n"
                "delivery_scope: 活动模板管理, 页面发布, 基础数据统计\n"
                "success_metrics: 创建耗时下降50%, 页面发布成功率95%\n"
                "constraints: 两周内上线, 复用现有账号体系"
            ),
        },
    )
    continue_body = continue_resp.json()
    print(continue_resp.status_code)
    print(
        {
            "turn_count": continue_body["turn_count"],
            "status": continue_body["status"],
            "can_generate_draft": continue_body["can_generate_draft"],
            "can_generate_final": continue_body["can_generate_final"],
            "facts_goal": continue_body["extracted_facts"]["goal"],
            "facts_open_questions": continue_body["extracted_facts"]["open_questions"][:2],
            "open_questions_count": len(continue_body["open_questions"]),
            "next_prompt": continue_body["next_prompt"],
        }
    )

    print("\nCASE: /prd/generate interactive draft")
    interactive_draft_resp = client.post(
        "/prd/generate",
        json={"session_id": start_body["session_id"], "quality": "draft"},
    )
    interactive_draft_body = interactive_draft_resp.json()
    print(interactive_draft_resp.status_code)
    print(
        {
            "mode": interactive_draft_body["mode"],
            "quality": interactive_draft_body["quality"],
            "status": interactive_draft_body["status"],
            "missing_information": interactive_draft_body["missing_information"],
            "markdown_head": interactive_draft_body["markdown"].splitlines()[:6],
        }
    )

    print("\nCASE: /prd/generate interactive final")
    interactive_final_resp = client.post(
        "/prd/generate",
        json={"session_id": start_body["session_id"]},
    )
    interactive_final_body = interactive_final_resp.json()
    print(interactive_final_resp.status_code)
    print(
        {
            "mode": interactive_final_body["mode"],
            "quality": interactive_final_body["quality"],
            "status": interactive_final_body["status"],
            "missing_information": interactive_final_body["missing_information"],
            "markdown_head": interactive_final_body["markdown"].splitlines()[:6],
        }
    )

    print("\nCASE: /prd/generate reverse (quality ignored)")
    reverse_resp = client.post(
        "/prd/generate",
        json={
            "mode": "reverse",
            "input_text": "这是一个面向运营团队的活动配置工具，帮助快速创建活动页面并提高转化。",
            "quality": "draft",
        },
    )
    reverse_body = reverse_resp.json()
    print(reverse_resp.status_code)
    print(
        {
            "mode": reverse_body["mode"],
            "quality": reverse_body["quality"],
            "status": reverse_body["status"],
            "missing_information": reverse_body["missing_information"],
            "markdown_head": reverse_body["markdown"].splitlines()[:6],
        }
    )

    print("\nCASE: 非法 shape")
    invalid_resp = client.post(
        "/prd/generate",
        json={"session_id": "abc", "mode": "interactive", "input_text": "bad"},
    )
    print(invalid_resp.status_code)
    print(invalid_resp.json())

    print("\nCASE: session 不存在")
    missing_session_resp = client.post(
        "/session/continue",
        json={"session_id": "missing-session", "input_text": "hello"},
    )
    print(missing_session_resp.status_code)
    print(missing_session_resp.json())


if __name__ == "__main__":
    main()
