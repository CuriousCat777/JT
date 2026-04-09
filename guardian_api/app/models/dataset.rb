class Dataset < ApplicationRecord
  validates :name, presence: true

  scope :stale, -> { where(stale: true) }
  scope :fresh, -> { where(stale: false) }
  scope :by_source, ->(source) { where(source: source) }

  def mark_stale!
    update!(stale: true)
  end

  def mark_fresh!
    update!(stale: false, downloaded_at: Time.current)
  end

  def file_exists?
    file_path.present? && File.exist?(file_path)
  end

  def size_human
    return "unknown" unless size_bytes

    units = %w[B KB MB GB TB]
    size = size_bytes.to_f
    unit_index = 0

    while size >= 1024 && unit_index < units.length - 1
      size /= 1024
      unit_index += 1
    end

    "#{size.round(1)} #{units[unit_index]}"
  end
end
