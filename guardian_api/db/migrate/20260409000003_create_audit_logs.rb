class CreateAuditLogs < ActiveRecord::Migration[7.2]
  def change
    create_table :audit_logs do |t|
      t.string :agent_name, null: false
      t.string :action, null: false
      t.string :severity, default: "info"
      t.json :details, default: {}

      t.datetime :created_at, null: false
    end

    add_index :audit_logs, :agent_name
    add_index :audit_logs, :severity
    add_index :audit_logs, :created_at
  end
end
