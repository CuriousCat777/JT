module Api
  module V1
    class DatasetsController < ApplicationController
      before_action :set_dataset, only: [:show, :refresh]

      # GET /api/v1/datasets
      def index
        datasets = Dataset.all.order(updated_at: :desc)
        datasets = datasets.by_source(params[:source]) if params[:source].present?
        datasets = datasets.stale if params[:stale] == "true"

        render json: { datasets: datasets }, status: :ok
      end

      # GET /api/v1/datasets/:id
      def show
        render json: {
          dataset: @dataset,
          file_exists: @dataset.file_exists?,
          size_human: @dataset.size_human
        }, status: :ok
      end

      # GET /api/v1/datasets/search?q=term
      def search
        query = params[:q].to_s.strip
        return render json: { error: "Query parameter 'q' is required" }, status: :bad_request if query.blank?

        datasets = Dataset.where("name LIKE ? OR source LIKE ?", "%#{query}%", "%#{query}%")
                          .order(updated_at: :desc)

        render json: { query: query, datasets: datasets }, status: :ok
      end

      # POST /api/v1/datasets/:id/refresh
      def refresh
        @dataset.mark_stale!

        AuditLog.create!(
          agent_name: "data_collector",
          action: "dataset_refresh_requested",
          severity: "info",
          details: { dataset_id: @dataset.id, name: @dataset.name }
        )

        render json: { dataset: @dataset.reload, message: "Dataset marked for refresh" }, status: :ok
      end

      private

      def set_dataset
        @dataset = Dataset.find(params[:id])
      rescue ActiveRecord::RecordNotFound
        render json: { error: "Dataset not found" }, status: :not_found
      end
    end
  end
end
