class CreateDevices < ActiveRecord::Migration[7.2]
  def change
    create_table :devices do |t|
      t.string :name, null: false
      t.string :category
      t.string :location
      t.string :protocol
      t.string :status, default: "offline"
      t.string :firmware
      t.string :ip_address

      t.timestamps
    end

    add_index :devices, :category
    add_index :devices, :location
    add_index :devices, :status
  end
end
