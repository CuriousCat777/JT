module Api
  module V1
    class DevicesController < ApplicationController
      before_action :set_device, only: [:show, :update]

      # GET /api/v1/devices
      def index
        devices = Device.all.order(:location, :name)
        devices = devices.by_category(params[:category]) if params[:category].present?
        devices = devices.in_room(params[:location]) if params[:location].present?
        devices = devices.where(status: params[:status]) if params[:status].present?

        render json: { devices: devices }, status: :ok
      end

      # GET /api/v1/devices/:id
      def show
        render json: { device: @device }, status: :ok
      end

      # PATCH /api/v1/devices/:id
      def update
        if @device.update(device_params)
          AuditLog.create!(
            agent_name: "device_agent",
            action: "device_updated",
            severity: "info",
            details: { device_id: @device.id, changes: @device.previous_changes }
          )

          render json: { device: @device }, status: :ok
        else
          render json: { errors: @device.errors.full_messages }, status: :unprocessable_entity
        end
      end

      # POST /api/v1/devices/scenes
      def scenes
        scene_name = params[:scene]
        return render json: { error: "Scene name is required" }, status: :bad_request if scene_name.blank?

        result = Device.activate_scene(scene_name)

        if result[:error]
          render json: result, status: :unprocessable_entity
        else
          AuditLog.create!(
            agent_name: "device_agent",
            action: "scene_activated",
            severity: "info",
            details: result
          )

          render json: result, status: :ok
        end
      end

      private

      def set_device
        @device = Device.find(params[:id])
      rescue ActiveRecord::RecordNotFound
        render json: { error: "Device not found" }, status: :not_found
      end

      def device_params
        params.require(:device).permit(:name, :category, :location, :protocol, :status, :firmware, :ip_address)
      end
    end
  end
end
