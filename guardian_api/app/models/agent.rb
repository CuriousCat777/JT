class Agent < ApplicationRecord
  validates :name, presence: true, uniqueness: true
  validates :status, inclusion: { in: %w[idle running error completed] }

  scope :active, -> { where(status: "running") }
  scope :errored, -> { where(status: "error") }

  # Trigger a Python Guardian agent via subprocess
  def trigger_run!
    update!(status: "running", last_run: Time.current)

    result = execute_python_agent
    update!(status: result[:success] ? "completed" : "error")

    AuditLog.create!(
      agent_name: name,
      action: "run",
      severity: result[:success] ? "info" : "error",
      details: { output: result[:output], exit_code: result[:exit_code] }
    )

    result
  rescue StandardError => e
    update!(status: "error")
    AuditLog.create!(
      agent_name: name,
      action: "run",
      severity: "error",
      details: { error: e.message }
    )
    { success: false, output: e.message, exit_code: -1 }
  end

  private

  def execute_python_agent
    guardian_root = Rails.root.join("..")
    cmd = "python main.py --agent #{name}"

    output = `cd #{guardian_root} && #{cmd} 2>&1`
    exit_code = $?.exitstatus

    { success: exit_code == 0, output: output.truncate(10_000), exit_code: exit_code }
  end
end
