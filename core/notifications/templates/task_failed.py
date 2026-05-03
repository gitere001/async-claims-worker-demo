from datetime import datetime


def render(
    task_name: str,
    claim_id: str | None,
    error: str,
    attempts: int,
    failed_at: datetime,
) -> tuple[str, str]:
    subject = f"[ALERT] Task failed — {task_name}"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #dc2626; padding: 16px 24px;">
            <h2 style="color: white; margin: 0;">Task Failed Alert</h2>
        </div>

        <div style="padding: 24px; border: 1px solid #e5e7eb;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px 0; color: #6b7280; width: 140px;">Task</td>
                    <td style="padding: 8px 0; font-weight: bold;">{task_name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #6b7280;">Claim ID</td>
                    <td style="padding: 8px 0;">{claim_id or "N/A"}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #6b7280;">Attempts</td>
                    <td style="padding: 8px 0;">{attempts}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #6b7280;">Failed at</td>
                    <td style="padding: 8px 0;">{failed_at.strftime("%Y-%m-%d %H:%M:%S UTC")}</td>
                </tr>
            </table>

            <div style="margin-top: 16px;">
                <p style="color: #6b7280; margin-bottom: 8px;">Error</p>
                <div style="background: #fef2f2; border-left: 4px solid #dc2626; padding: 12px; font-family: monospace; font-size: 13px; white-space: pre-wrap;">{error}</div>
            </div>

            <div style="margin-top: 24px; padding: 16px; background: #f9fafb; border-radius: 4px;">
                <p style="margin: 0; font-weight: bold;">Next steps</p>
                <ol style="margin: 8px 0 0 0; padding-left: 20px; color: #374151;">
                    <li>Check the <code>failed_tasks</code> table for the full payload</li>
                    <li>Read the error and identify the root cause</li>
                    <li>Fix the issue</li>
                    <li>Replay the claim using the payload from <code>failed_tasks</code></li>
                </ol>
            </div>
        </div>

        <div style="padding: 16px 24px; color: #9ca3af; font-size: 12px;">
            Async Claims Worker — automated alert
        </div>
    </div>
    """

    return subject, html
