module Api
  module V1
    class HealthController < ApplicationController
      # GET /health
      def show
        health = {
          status: "ok",
          service: "Guardian One API",
          version: "1.0.0",
          timestamp: Time.current.iso8601,
          ruby: RUBY_VERSION,
          rails: Rails::VERSION::STRING,
          database: database_status,
          agents: agent_summary
        }

        status_code = health[:database][:connected] ? :ok : :service_unavailable
        render json: health, status: status_code
      end

      private

      def database_status
        ActiveRecord::Base.connection.execute("SELECT 1")
        { connected: true, adapter: ActiveRecord::Base.connection.adapter_name }
      rescue StandardError => e
        { connected: false, error: e.message }
      end

      def agent_summary
        {
          total: Agent.count,
          running: Agent.where(status: "running").count,
          errored: Agent.where(status: "error").count
        }
      rescue StandardError
        { total: 0, running: 0, errored: 0 }
      end
    end
  end
end
