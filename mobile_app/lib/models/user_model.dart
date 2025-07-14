// lib/models/user_model.dart
class User {
  final String id;
  final String name;
  final String email;
  final String role;
  final String? avatar; // Can be null or default path
  final String dateAdded; // Expecting ISO format string from server

  User({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    this.avatar,
    required this.dateAdded,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] ?? '',
      name: json['name'] ?? 'N/A',
      email: json['email'] ?? 'N/A',
      role: json['role'] ?? 'N/A',
      avatar: json['avatar'], // Keep as potentially null or default string
      dateAdded: json['dateAdded'] ?? '',
    );
  }
}
