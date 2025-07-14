// lib/models/log_model.dart
class Log {
  final int
      id; // Assuming server returns an ID for logs, useful for keys/intruder image URL
  final String
      type; // e.g., "Access", "Intruder", "System", "Keypad Success", "Keypad Failure"
  final String details;
  final String date; // e.g., "MM/DD/YYYY" as returned by server
  final String timestamp; // e.g., "HH:MM:SS" as returned by server
  final Map<String, dynamic>? user; // User info map {id, name, avatar} or null
  final String? imagePath; // Relative path for intruder image or null

  Log({
    required this.id,
    required this.type,
    required this.details,
    required this.date,
    required this.timestamp,
    this.user,
    this.imagePath,
  });

  factory Log.fromJson(Map<String, dynamic> json) {
    return Log(
      id: json['id'] ?? 0, // Provide default or handle error if ID is missing
      type: json['type'] ?? 'Unknown',
      details: json['details'] ?? '',
      date: json['date'] ?? '',
      timestamp: json['timestamp'] ?? '',
      user: json['user'] != null && json['user'] is Map<String, dynamic>
          ? json['user']
          : null,
      imagePath: json['image_path'], // Keep as potentially null
    );
  }

  // Helper to combine date and time for sorting, if needed later
  // DateTime getDateTime() {
  //   try {
  //     // Assumes MM/DD/YYYY HH:MM:SS format for parsing
  //     final parts = date.split('/');
  //     final timeParts = timestamp.split(':');
  //     if (parts.length == 3 && timeParts.length == 3) {
  //       return DateTime(
  //         int.parse(parts[2]), int.parse(parts[0]), int.parse(parts[1]),
  //         int.parse(timeParts[0]), int.parse(timeParts[1]), int.parse(timeParts[2])
  //       );
  //     }
  //   } catch (e) {
  //     print("Error parsing log date/time: $e");
  //   }
  //   // Return epoch if parsing fails to allow some sorting
  //   return DateTime.fromMillisecondsSinceEpoch(0);
  // }
}
