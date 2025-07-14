// lib/services/api_service.dart
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data'; // <-- Import Uint8List
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ApiService {
  // !! IMPORTANT: Replace with your PC's ACTUAL local IP address !!
  // Use 10.0.2.2 for Android Emulator accessing localhost on the host machine
  // Use http://<Your-PC-IP>:5000 for a physical device on the same network
  final String _baseUrl = ""; // CHANGE THIS

  // --- Helper Functions ---

  // Gets headers, adding Auth token if requireAuth is true
  Future<Map<String, String>> _getHeaders(
      {bool requireAuth = true, bool isJson = true}) async {
    final Map<String, String> headers = {};
    if (isJson) {
      headers['Content-Type'] = 'application/json; charset=UTF-8';
      headers['Accept'] = 'application/json';
    }

    if (requireAuth) {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('neuralock_token');
      if (token != null) {
        headers['Authorization'] = 'Bearer $token';
      } else {
        print("Warning: Auth token required by _getHeaders but not found.");
      }
    }
    return headers;
  }

  dynamic _handleResponse(http.Response response) {
    try {
      final data = jsonDecode(response.body);
      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (data != null && data is Map && data['status'] == 'success') {
          return data;
        } else if (data != null && data is Map && data['status'] == 'error') {
          throw Exception(data['message'] ?? 'API returned error status');
        } else {
          print(
              "Warning: Successful status code but unexpected payload format: ${response.body}");
          return data; // Return data as is
        }
      } else {
        String errorMessage = 'API request failed';
        if (data != null && data is Map && data['message'] != null) {
          errorMessage = data['message'];
        } else {
          errorMessage =
              'API request failed with status ${response.statusCode}';
        }
        print("API Error Response Body: ${response.body}");
        throw Exception(errorMessage);
      }
    } catch (e) {
      // Catch JSON decode errors too
      print("Error handling response: $e. Body: ${response.body}");
      // Throw a more generic error if JSON parsing fails on error response
      if (response.statusCode >= 400) {
        throw Exception(
            'API request failed with status ${response.statusCode}');
      }
      rethrow; // Rethrow original error if not an HTTP error status
    }
  }

  // --- Auth ---
  Future<Map<String, dynamic>> login(String email, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/login'),
        headers: {'Content-Type': 'application/json; charset=UTF-8'},
        body: jsonEncode({'email': email, 'password': password}),
      );
      final data = _handleResponse(response);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('neuralock_token', data['token']);
      return data['user'];
    } catch (e) {
      print("Login Error: $e");
      rethrow;
    }
  }

  // --- Global PIN ---
  Future<bool> getGlobalPinStatus() async {
    try {
      final headers = await _getHeaders();
      final response = await http.get(
          Uri.parse('$_baseUrl/api/settings/global-pin-status'),
          headers: headers);
      final data = _handleResponse(response);
      return data['is_set'] ?? false;
    } catch (e) {
      print("Error getting PIN status: $e");
      return true;
    }
  }

  Future<bool> verifyGlobalPin(String currentPin) async {
    try {
      final headers = await _getHeaders();
      final response = await http.post(
        Uri.parse('$_baseUrl/api/settings/global-pin/verify'),
        headers: headers,
        body: jsonEncode({'current_pin': currentPin}),
      );
      return response.statusCode == 200;
    } catch (e) {
      print("Error verifying Global PIN: $e");
      return false;
    }
  }

  Future<void> updateGlobalPin(String newPin) async {
    try {
      final headers = await _getHeaders();
      final response = await http.put(
        Uri.parse('$_baseUrl/api/settings/global-pin'),
        headers: headers,
        body: jsonEncode({'new_pin': newPin}),
      );
      _handleResponse(response);
    } catch (e) {
      print("Error updating Global PIN: $e");
      rethrow;
    }
  }

  // --- Users ---
  Future<List<dynamic>> getUsers() async {
    try {
      final headers = await _getHeaders();
      final response =
          await http.get(Uri.parse('$_baseUrl/api/users'), headers: headers);
      final data = _handleResponse(response);
      return data['users'] ?? [];
    } catch (e) {
      print("Error getting users: $e");
      rethrow;
    }
  }

  Future<Map<String, dynamic>> createUser(Map<String, dynamic> userData) async {
    try {
      final headers = await _getHeaders();
      final response = await http.post(
        Uri.parse('$_baseUrl/api/users'),
        headers: headers,
        body: jsonEncode(userData),
      );
      if (response.statusCode == 201) {
        final data = jsonDecode(response.body);
        if (data['status'] == 'success') return data['user'];
      }
      throw Exception(
          _handleResponse(response)['message'] ?? 'Failed to create user');
    } catch (e) {
      print("Error creating user: $e");
      rethrow;
    }
  }

  Future<void> deleteUser(String userId) async {
    try {
      final headers = await _getHeaders();
      final response = await http
          .delete(Uri.parse('$_baseUrl/api/users/$userId'), headers: headers);
      _handleResponse(response);
    } catch (e) {
      print("Error deleting user: $e");
      rethrow;
    }
  }

  // --- User Images (Faces) ---
  Future<List<dynamic>> getUserImages(String userId) async {
    try {
      final headers = await _getHeaders();
      final response = await http.get(
          Uri.parse('$_baseUrl/api/users/$userId/images'),
          headers: headers);
      final data = _handleResponse(response);
      return data['images'] ?? [];
    } catch (e) {
      print("Error getting user images: $e");
      rethrow;
    }
  }

  Future<String> uploadUserImage(String userId, File imageFile) async {
    try {
      final headers = await _getHeaders(
          requireAuth: true, isJson: false); // Auth needed, not JSON
      headers.remove('Content-Type');

      var request = http.MultipartRequest(
          'POST', Uri.parse('$_baseUrl/api/users/$userId/images'));
      request.headers.addAll(headers);
      request.files.add(await http.MultipartFile.fromPath(
        'file',
        imageFile.path,
        contentType: MediaType('image', 'jpeg'),
      ));

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);
      final data = _handleResponse(response); // Checks for success/error status

      // ---> Return filename from successful response <---
      if (data != null && data is Map && data['filename'] != null) {
        return data['filename'];
      } else {
        throw Exception(
            "Upload succeeded but filename was missing in response.");
      }
    } catch (e) {
      print("Error uploading user image: $e");
      rethrow;
    }
  }

  Future<void> deleteUserImage(String userId, String filename) async {
    try {
      final headers = await _getHeaders();
      final response = await http.delete(
          Uri.parse('$_baseUrl/api/users/$userId/images/$filename'),
          headers: headers);
      _handleResponse(response);
    } catch (e) {
      print("Error deleting user image: $e");
      rethrow;
    }
  }

  Future<void> setProfileImage(String userId, String filename) async {
    try {
      final headers = await _getHeaders();
      // The endpoint expects the filename of the image within known_faces
      final response = await http.put(
        Uri.parse('$_baseUrl/api/users/$userId/set-avatar'),
        headers: headers,
        body: jsonEncode({'filename': filename}), // Send filename to use
      );
      _handleResponse(response);
    } catch (e) {
      print("Error setting profile image from user image: $e");
      rethrow;
    }
  }

  // --- Profile ---
  Future<Map<String, dynamic>> getProfile() async {
    try {
      final headers = await _getHeaders();
      final response =
          await http.get(Uri.parse('$_baseUrl/api/profile'), headers: headers);
      final data = _handleResponse(response);
      return data['user'];
    } catch (e) {
      print("Error getting profile: $e");
      rethrow;
    }
  }

  Future<void> updateProfile(Map<String, dynamic> profileData) async {
    try {
      final headers = await _getHeaders();
      final response = await http.put(
        Uri.parse('$_baseUrl/api/profile'),
        headers: headers,
        body: jsonEncode(profileData),
      );
      _handleResponse(response);
    } catch (e) {
      print("Error updating profile: $e");
      rethrow;
    }
  }



  // --- Logs ---
  Future<List<dynamic>> getLogs({String? type}) async {
    try {
      final headers = await _getHeaders();
      String url = '$_baseUrl/api/logs';
      if (type != null && type != "All") {
        url += '?type=${Uri.encodeComponent(type)}';
      }
      final response = await http.get(Uri.parse(url), headers: headers);
      final data = _handleResponse(response);
      return data['logs'] ?? [];
    } catch (e) {
      print("Error getting logs: $e");
      rethrow;
    }
  }

  Future<void> controlPiStream(String piIpAddress, bool startStream) async {
    final String piCommandUrl =
        "http://$piIpAddress:8080"; // Use port 8080 for commands
    final String endpoint = startStream ? '/start_stream' : '/stop_stream';
    print("ApiService: Sending command '$endpoint' to Pi at $piCommandUrl");

    try {
      // Make the POST request (without timeout parameter)
      final requestFuture = http.post(
        Uri.parse('$piCommandUrl$endpoint'),
        headers: {'Content-Type': 'application/json; charset=UTF-8'},
        // No body needed
      );

      // Apply the timeout to the Future returned by http.post
      final response = await requestFuture.timeout(
        Duration(seconds: 5), // Apply 5-second timeout here
        onTimeout: () {
          // This callback executes if the timeout occurs
          print("ApiService: Pi stream control request timed out.");
          // Return a specific response or throw a timeout error
          // http.Response prevents needing null checks later, but indicates timeout
          return http.Response(
              '{"status":"error", "message":"Request timed out"}',
              408); // 408 Request Timeout
        },
      );

      // Check the response status code AFTER the timeout handling
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        print("ApiService: Pi stream control response: $data");
        if (data['status'] != 'success') {
          throw Exception("Pi returned non-success status for stream control.");
        }
      } else if (response.statusCode == 408) {
        // Handle timeout response specifically
        throw Exception('Request to Pi timed out');
      } else {
        throw Exception(
            'Failed to send stream command to Pi (Status code: ${response.statusCode})');
      }
    } catch (e) {
      print("Error controlling Pi stream: $e");
      rethrow;
    }
  }

  // --- Helper to get full image URL ---
  String getImageUrl(String? relativePath) {
    if (relativePath == null ||
        relativePath.isEmpty ||
        relativePath == 'default_avatar.png') return '';
    if (relativePath.startsWith('/')) relativePath = relativePath.substring(1);
    // Ensure no double slashes if base URL ends with / and path starts with /
    String separator =
        (_baseUrl.endsWith('/') || relativePath.startsWith('/')) &&
                !(_baseUrl.endsWith('/') && relativePath.startsWith('/'))
            ? ''
            : '/';
    if (_baseUrl.endsWith('/') && relativePath.startsWith('/')) {
      relativePath = relativePath.substring(1);
      separator = '/';
    }
    return '$_baseUrl$separator$relativePath';
  }

  // --- Helper to fetch authenticated image data ---
  Future<Uint8List> getAuthenticatedImage(String relativePath) async {
    if (relativePath.isEmpty) throw Exception("Empty image path");
    // Get headers WITH auth token, but remove JSON content type
    final headers = await _getHeaders(requireAuth: true, isJson: false);

    final imageUrl = getImageUrl(relativePath); 

    try {
      final response = await http.get(Uri.parse(imageUrl), headers: headers);
      if (response.statusCode == 200) {
        return response.bodyBytes; // Return raw image bytes on success
      } else {
        // Attempt to parse JSON error message if available
        String errorMessage =
            'Failed to load image (Status code: ${response.statusCode})';
        try {
          final errorData = jsonDecode(response.body);
          errorMessage = errorData['message'] ?? errorMessage;
        } catch (_) {/* Ignore if response body isn't valid JSON */}
        throw Exception(errorMessage);
      }
    } catch (e) {
      // Catch network errors etc.
      print("Error fetching authenticated image '$imageUrl': $e");
      rethrow; // Let UI handle specific error
    }
  }

  Future<void> changePassword(
      String currentPassword, String newPassword) async {
    try {
      final headers = await _getHeaders(); // Requires auth
      final response = await http.put(
        Uri.parse('$_baseUrl/api/profile/password'),
        headers: headers,
        body: jsonEncode({
          'current_password': currentPassword,
          'new_password': newPassword,
        }),
      );
      _handleResponse(response); // Throws exception on failure
    } catch (e) {
      print("Error changing password: $e");
      rethrow;
    }
  }

  // --- Debug (Keep or remove) ---
  Future<Map<String, dynamic>> checkImageExists(
      String userId, String filename) async {
    /* ... */ final headers = await _getHeaders();
    final imageUrl = getImageUrl('known_faces/$userId/$filename');
    try {
      final response = await http.head(Uri.parse(imageUrl), headers: headers);
      return {
        'url_checked': imageUrl,
        'exists': response.statusCode == 200,
        'status_code': response.statusCode,
      };
    } catch (e) {
      return {
        'url_checked': imageUrl,
        'exists': false,
        'error': e.toString(),
      };
    }
  }
}
