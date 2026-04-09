class Device < ApplicationRecord
  validates :name, presence: true
  validates :status, inclusion: { in: %w[online offline error maintenance] }

  scope :online, -> { where(status: "online") }
  scope :offline, -> { where(status: "offline") }
  scope :in_room, ->(location) { where(location: location) }
  scope :by_category, ->(category) { where(category: category) }
  scope :by_protocol, ->(protocol) { where(protocol: protocol) }

  SCENES = {
    "movie" => { lights: "dim", tv: "on", blinds: "closed" },
    "work" => { lights: "bright", music: "focus", notifications: "dnd" },
    "away" => { lights: "off", security: "armed", hvac: "eco" },
    "goodnight" => { lights: "off", doors: "locked", hvac: "sleep" }
  }.freeze

  def self.activate_scene(scene_name)
    scene = SCENES[scene_name]
    return { error: "Unknown scene: #{scene_name}" } unless scene

    { scene: scene_name, config: scene, activated_at: Time.current }
  end
end
