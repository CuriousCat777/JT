class CreateAgents < ActiveRecord::Migration[7.2]
  def change
    create_table :agents do |t|
      t.string :name, null: false, index: { unique: true }
      t.string :status, default: "idle"
      t.datetime :last_run
      t.json :config, default: {}

      t.timestamps
    end
  end
end
