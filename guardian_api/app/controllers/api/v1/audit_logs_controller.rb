module Api
  module V1
    class AuditLogsController < ApplicationController
      # GET /api/v1/audit_logs
      def index
        logs = AuditLog.order(created_at: :desc)
        logs = logs.by_agent(params[:agent]) if params[:agent].present?
        logs = logs.by_severity(params[:severity]) if params[:severity].present?

        limit = (params[:limit] || 100).to_i.clamp(1, 1000)
        logs = logs.limit(limit)

        render json: { audit_logs: logs, count: logs.size }, status: :ok
      end
    end
  end
end
