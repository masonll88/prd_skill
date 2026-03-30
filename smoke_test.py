"""Minimal local smoke tests for the prd_skill service."""

from fastapi.testclient import TestClient

from app import app


def main() -> None:
    """Run the minimal integration checks requested for the service."""

    client = TestClient(app)

    print("CASE: /session/start")
    start_resp = client.post("/session/start", json={"mode": "interactive"})
    start_body = start_resp.json()
    print(start_resp.status_code)
    print(
        {
            "session_id": start_body["session_id"],
            "status": start_body["status"],
            "can_generate": start_body["can_generate"],
            "missing_information": start_body["missing_information"],
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
                "conversion_path: 进入后台, 创建活动, 发布上线"
            ),
        },
    )
    continue_body = continue_resp.json()
    print(continue_resp.status_code)
    print(
        {
            "status": continue_body["status"],
            "can_generate": continue_body["can_generate"],
            "missing_information": continue_body["missing_information"],
        }
    )

    print("\nCASE: /prd/generate interactive")
    interactive_prd_resp = client.post(
        "/prd/generate", json={"session_id": start_body["session_id"]}
    )
    interactive_prd_body = interactive_prd_resp.json()
    print(interactive_prd_resp.status_code)
    print(
        {
            "mode": interactive_prd_body["mode"],
            "status": interactive_prd_body["status"],
            "missing_information": interactive_prd_body["missing_information"],
            "markdown_head": interactive_prd_body["markdown"].splitlines()[:4],
        }
    )

    print("\nCASE: /prd/generate reverse")
    reverse_resp = client.post(
        "/prd/generate",
        json={
            "mode": "reverse",
            "input_text": "这是一个面向运营团队的活动配置工具，帮助快速创建活动页面并提高转化。",
        },
    )
    reverse_body = reverse_resp.json()
    print(reverse_resp.status_code)
    print(
        {
            "mode": reverse_body["mode"],
            "status": reverse_body["status"],
            "missing_information": reverse_body["missing_information"],
            "markdown_head": reverse_body["markdown"].splitlines()[:4],
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
