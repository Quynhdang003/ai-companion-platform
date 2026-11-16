import type { RiskLevel, ScamType } from "@/lib/api/schemas";

/** Same names as the family's Telegram alerts (backend `notification/messages.py`). */
export const scamTypeLabels: Record<ScamType, string> = {
  police_impersonation: "Giả danh công an, viện kiểm sát, tòa án",
  bank_impersonation: "Giả danh nhân viên ngân hàng",
  relative_impersonation: "Giả danh con cháu hoặc người quen",
  investment: "Mời đầu tư lãi cao",
  health_product: "Bán thuốc, thực phẩm chức năng",
  resort_contract: "Hợp đồng du lịch, nghỉ dưỡng",
  fake_charity: "Kêu gọi từ thiện giả",
  other: "Kiểu lừa đảo khác",
};

export const riskLevelLabels: Record<RiskLevel, string> = {
  high: "Nguy cơ cao",
  medium: "Nguy cơ trung bình",
  low: "Nguy cơ thấp",
  none: "Không có nguy cơ",
};
