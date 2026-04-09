class AuditLog < ApplicationRecord
  # Audit logs are append-only: no updates or deletes
  validates :agent_name, presence: true
  validates :action, presence: true
  validates :severity, inclusion: { in: %w[debug info warn error critical] }

  scope :by_agent, ->(name) { where(agent_name: name) }
  scope :by_severity, ->(severity) { where(severity: severity) }
  scope :recent, ->(limit = 50) { order(created_at: :desc).limit(limit) }
  scope :errors, -> { where(severity: %w[error critical]) }

  # Prevent updates — audit logs are immutable
  def readonly?
    persisted?
  end
end
