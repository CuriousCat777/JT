Rails.application.routes.draw do
  # Health check at /health (top-level for load balancers)
  get "health", to: "api/v1/health#show"

  # Built-in Rails health check
  get "up" => "rails/health#show", as: :rails_health_check

  # API v1 namespace
  namespace :api do
    namespace :v1 do
      # Agents
      resources :agents, only: [:index, :show] do
        member do
          post :run
        end
      end

      # Datasets
      resources :datasets, only: [:index, :show] do
        collection do
          get :search
        end
        member do
          post :refresh
        end
      end

      # Audit Logs (read-only)
      resources :audit_logs, only: [:index]

      # Devices
      resources :devices, only: [:index, :show, :update] do
        collection do
          post :scenes
        end
      end

      # Health (also available under namespace)
      get "health", to: "health#show"
    end
  end
end
