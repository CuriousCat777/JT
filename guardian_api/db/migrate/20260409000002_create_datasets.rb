class CreateDatasets < ActiveRecord::Migration[7.2]
  def change
    create_table :datasets do |t|
      t.string :name, null: false
      t.string :source
      t.string :url
      t.string :file_path
      t.json :schema_info, default: {}
      t.string :sha256
      t.bigint :size_bytes
      t.datetime :downloaded_at
      t.boolean :stale, default: false

      t.timestamps
    end

    add_index :datasets, :name
    add_index :datasets, :source
    add_index :datasets, :stale
  end
end
