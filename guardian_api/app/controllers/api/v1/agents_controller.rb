module Api
  module V1
    class AgentsController < ApplicationController
      before_action :set_agent, only: [:show, :run]

      # GET /api/v1/agents
      def index
        agents = Agent.all.order(:name)
        render json: { agents: agents }, status: :ok
      end

      # GET /api/v1/agents/:id
      def show
        render json: { agent: @agent }, status: :ok
      end

      # POST /api/v1/agents/:id/run
      def run
        result = @agent.trigger_run!

        render json: {
          agent: @agent.reload,
          result: {
            success: result[:success],
            output: result[:output],
            exit_code: result[:exit_code]
          }
        }, status: result[:success] ? :ok : :unprocessable_entity
      end

      private

      def set_agent
        @agent = Agent.find(params[:id])
      rescue ActiveRecord::RecordNotFound
        render json: { error: "Agent not found" }, status: :not_found
      end
    end
  end
end
