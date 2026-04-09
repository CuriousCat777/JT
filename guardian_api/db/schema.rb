# This file is auto-generated from the current state of the database. Instead
# of editing this file, please use the migrations feature of Active Record to
# incrementally modify your database, and then regenerate this schema definition.
#
# This file is the source Rails uses to define your schema when running `bin/rails
# db:schema:load`. When creating a new database, `bin/rails db:schema:load` tends to
# be faster and is potentially less error prone than running all of your
# migrations from scratch. Old migrations may fail to apply correctly if those
# migrations use external dependencies or application code.
#
# It's strongly recommended that you check this file into your version control system.

ActiveRecord::Schema[7.2].define(version: 2026_04_09_000004) do
  create_table "agents", force: :cascade do |t|
    t.string "name", null: false
    t.string "status", default: "idle"
    t.datetime "last_run"
    t.json "config", default: {}
    t.datetime "created_at", null: false
    t.datetime "updated_at", null: false
    t.index ["name"], name: "index_agents_on_name", unique: true
  end

  create_table "audit_logs", force: :cascade do |t|
    t.string "agent_name", null: false
    t.string "action", null: false
    t.string "severity", default: "info"
    t.json "details", default: {}
    t.datetime "created_at", null: false
    t.index ["agent_name"], name: "index_audit_logs_on_agent_name"
    t.index ["created_at"], name: "index_audit_logs_on_created_at"
    t.index ["severity"], name: "index_audit_logs_on_severity"
  end

  create_table "datasets", force: :cascade do |t|
    t.string "name", null: false
    t.string "source"
    t.string "url"
    t.string "file_path"
    t.json "schema_info", default: {}
    t.string "sha256"
    t.bigint "size_bytes"
    t.datetime "downloaded_at"
    t.boolean "stale", default: false
    t.datetime "created_at", null: false
    t.datetime "updated_at", null: false
    t.index ["name"], name: "index_datasets_on_name"
    t.index ["source"], name: "index_datasets_on_source"
    t.index ["stale"], name: "index_datasets_on_stale"
  end

  create_table "devices", force: :cascade do |t|
    t.string "name", null: false
    t.string "category"
    t.string "location"
    t.string "protocol"
    t.string "status", default: "offline"
    t.string "firmware"
    t.string "ip_address"
    t.datetime "created_at", null: false
    t.datetime "updated_at", null: false
    t.index ["category"], name: "index_devices_on_category"
    t.index ["location"], name: "index_devices_on_location"
    t.index ["status"], name: "index_devices_on_status"
  end
end
