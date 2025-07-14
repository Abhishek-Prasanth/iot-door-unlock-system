// lib/screens/profile_screen.dart

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neuralock/utils/app_colors.dart';
import 'package:neuralock/services/api_service.dart'; // Import ApiService
import 'package:image_picker/image_picker.dart';
import 'dart:io'; // For File type
import 'dart:typed_data';
import 'dart:math';

class ProfileScreen extends StatefulWidget {
  @override
  _ProfileScreenState createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _isLoading = true;
  bool _isEditing = false;
  bool _isSaving = false;
  bool _isUploading = false; // Combined state for pick/upload/set avatar

  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();

  String _selectedRole = '';
  String? _profileImagePath; // Relative path like known_faces/USER_ID/file.jpg
  String _dateAdded = '';
  String? _currentUserId; // Store the logged-in user's ID

  final ApiService _apiService = ApiService();
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadProfileData();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _loadProfileData() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final profileData = await _apiService.getProfile();
      if (!mounted) return;
      setState(() {
        _currentUserId = profileData['id']; // <-- Store user ID
        _nameController.text = profileData['name'] ?? 'N/A';
        _emailController.text = profileData['email'] ?? 'N/A';
        _phoneController.text = profileData['phone'] ?? '';
        _selectedRole = profileData['role'] ?? 'N/A';
        _profileImagePath = profileData['avatar'];
        _dateAdded = profileData['dateAdded'] != null
            ? profileData['dateAdded'].split('T')[0]
            : 'N/A';
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage =
            "Error loading profile: ${e.toString().replaceFirst('Exception: ', '')}";
      });
      _showErrorSnackbar(_errorMessage!);
    }
  }

  // Handle logout action
  Future<void> _handleLogout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('neuralock_token');
    // Navigate to login and remove all previous routes
    Navigator.of(context)
        .pushNamedAndRemoveUntil('/login', (Route<dynamic> route) => false);
  }

  // Pick image from gallery and upload as avatar
  Future<void> _pickImage() async {
    if (_isUploading || _currentUserId == null) return;
    setState(() {
      _isUploading = true;
      _errorMessage = null;
    });
    try {
      final ImagePicker picker = ImagePicker();
      final XFile? pickedFile =
          await picker.pickImage(source: ImageSource.gallery, imageQuality: 80);
      if (pickedFile == null) {
        setState(() => _isUploading = false);
        return;
      } // User cancelled
      if (!mounted) return;

      final newFilename = await _apiService.uploadUserImage(
          _currentUserId!, File(pickedFile.path));
      if (!mounted) return;

      await _apiService.setProfileImage(_currentUserId!, newFilename);
      if (!mounted) return;

      _showSuccessSnackbar('Profile image updated successfully!');
      await _loadProfileData(); // Reload to show new avatar
    } catch (e) {
      if (!mounted) return;
      _showErrorSnackbar(
          "Error updating profile image: ${e.toString().replaceFirst('Exception: ', '')}");
    } finally {
      if (mounted) {
        setState(() {
          _isUploading = false;
        });
      }
    }
  }

  // Toggle between viewing and editing mode
  void _toggleEditMode() {
    if (!mounted) return;
    setState(() {
      _isEditing = !_isEditing;
      _errorMessage = null; // Clear errors when switching modes
      // If cancelling edit, reload data to discard changes
      if (!_isEditing) {
        _loadProfileData();
      }
    });
  }

  // Save edited profile information to the server
  Future<void> _saveProfile() async {
    if (!mounted || _isSaving) return;
    setState(() {
      _isSaving = true;
      _errorMessage = null;
    });
    try {
      final Map<String, dynamic> updatedData = {
        'name': _nameController.text,
        'email': _emailController.text,
        'role': _selectedRole,
        'phone': _phoneController.text, // <-- Include phone number
      };
      await _apiService.updateProfile(updatedData);
      if (!mounted) return;
      setState(() {
        _isEditing = false;
      }); // Exit edit mode
      _showSuccessSnackbar('Profile updated successfully');
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage =
            "Error saving profile: ${e.toString().replaceFirst('Exception: ', '')}";
      });
      _showErrorSnackbar(_errorMessage!);
    } finally {
      if (mounted) {
        setState(() {
          _isSaving = false;
        });
      }
    }
  }

  void _showChangePasswordDialog() {
    showDialog(
      context: context,
      barrierDismissible: false, // User must tap button
      builder: (context) =>
          ChangePasswordDialog(apiService: _apiService), // Use separate widget
    );
  }
  // --- Helper UI Methods ---
  //String? _errorMessage; // Store error message for display

  void _showErrorSnackbar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red[600]),
    );
  }

  void _showSuccessSnackbar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.green[600]),
    );
  }

  // --- Build Methods ---

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _buildAppBar(),
          Expanded(
            child: _isLoading && _profileImagePath == null
                ? Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _loadProfileData,
                    child: SingleChildScrollView(
                      physics: AlwaysScrollableScrollPhysics(),
                      padding: EdgeInsets.all(16),
                      child: Column(
                        children: [
                          // Display error message if any
                          if (_errorMessage != null && !_isLoading)
                            Container(
                              padding: EdgeInsets.all(12),
                              margin: EdgeInsets.only(bottom: 16),
                              decoration: BoxDecoration(
                                color: Colors.red[50],
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: Colors.red[100]!),
                              ),
                              child: Text(
                                _errorMessage!,
                                style: TextStyle(color: Colors.red[700]),
                              ),
                            ),

                          _buildProfileHeader(),
                          SizedBox(height: 16),
                          _buildPersonalInfo(),
                          SizedBox(height: 16),
                          // --- ADD Change Password Button ---
                          _buildChangePasswordButton(),
                          SizedBox(height: 16),
                          // -------------------------------
                          _buildLogoutButton(),
                          SizedBox(height: 16),
                        ],
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildAppBar() {
    // ... (AppBar structure remains the same) ...
    return Container(
      padding: EdgeInsets.fromLTRB(
          16, MediaQuery.of(context).padding.top + 8, 16, 16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.primary, AppColors.primaryLight],
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          GestureDetector(
            onTap: () => Navigator.pop(context),
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: AppColors.secondaryWithOpacity(0.3),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Icon(
                Icons.arrow_back,
                color: Colors.white,
                size: 20,
              ),
            ),
          ),
          Text(
            'Profile',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(width: 40),
        ],
      ),
    );
  }

  Widget _buildProfileHeader() {
    // Builds avatar, name, role, edit button section
    return Container(
      decoration: BoxDecoration(
        /* Card Styling */ color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.secondaryWithOpacity(0.2)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.03),
            blurRadius: 10,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        children: [
          Container(
            height: 100,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [AppColors.primary, AppColors.primaryLight],
              ),
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
              ),
            ),
          ),
          Container(
            transform: Matrix4.translationValues(0, -50, 0),
            margin: EdgeInsets.only(bottom: _isEditing ? 16 : -30),
            padding: EdgeInsets.only(bottom: _isEditing ? 0 : 16),
            child: Column(
              children: [
                Stack(
                  alignment: Alignment.center,
                  children: [
                    // Avatar
                    Container(
                      width: 100,
                      height: 100,
                      decoration: BoxDecoration(
                        color: Colors.grey[200],
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 4),
                      ),
                      child: ClipRRect(
                          borderRadius: BorderRadius.circular(50),
                          child: _buildAuthenticatedImage(_profileImagePath,
                              width: 100, height: 100)),
                    ),
                    Positioned(
                      bottom: 0,
                      right: 0,
                      child: GestureDetector(
                        onTap: _isUploading ? null : _pickImage,
                        child: Container(
                            padding: EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: AppColors.secondary,
                              shape: BoxShape.circle,
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.1),
                                  blurRadius: 4,
                                  offset: Offset(0, 2),
                                ),
                              ],
                            ),
                            child: _isUploading
                                ? SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        valueColor: AlwaysStoppedAnimation(
                                            Colors.white)))
                                : Icon(
                                    Icons.camera_alt,
                                    color: Colors.white,
                                    size: 16,
                                  )),
                      ),
                    ),
                  ],
                ),
                SizedBox(height: 16),
                _isEditing
                    ? _buildEditProfileForm()
                    : _buildProfileInfo(), // Name/Role/Edit or View Mode
              ],
            ),
          ),
        ],
      ),
    );
  }

  // Shows Name, Role, and Edit button in View mode
  Widget _buildProfileInfo() {
    return Column(
      children: [
        Text(
          _nameController.text,
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.bold,
            color: AppColors.primary,
          ),
          textAlign: TextAlign.center,
        ),
        SizedBox(height: 4),
        Text(
          _selectedRole,
          style: TextStyle(
            fontSize: 14,
            color: Colors.grey[600],
          ),
        ),
        SizedBox(height: 12),
        // Edit Button
        TextButton.icon(
          onPressed: _isLoading || _isSaving || _isUploading
              ? null
              : _toggleEditMode, // Disable while loading/saving
          icon: Icon(
            Icons.edit,
            size: 16,
            color: AppColors.primary,
          ),
          label: Text(
            'Edit Profile',
            style: TextStyle(
              color: AppColors.primary,
              fontSize: 14,
            ),
          ),
          style: TextButton.styleFrom(
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          ),
        ),
      ],
    );
  }

  // Shows editable fields and Save/Cancel buttons in Edit mode
  Widget _buildEditProfileForm() {
    // Edit form with Name, Role, Save/Cancel
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          TextField(
            controller: _nameController,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: AppColors.primary,
            ),
            decoration: InputDecoration(
              isDense: true,
              contentPadding:
                  EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              labelText: "Name",
            ),
          ),
          SizedBox(height: 12),
          // --- Add Phone Number TextField Here ---
          TextField(
            controller: _phoneController,
            textAlign: TextAlign.center,
            keyboardType: TextInputType.phone,
            style: TextStyle(
              fontSize: 16,
              /*fontWeight: FontWeight.bold,*/ color: AppColors.textPrimary,
            ),
            decoration: InputDecoration(
              isDense: true,
              contentPadding:
                  EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              labelText: "Phone",
            ),
          ),
          SizedBox(height: 12),
          // --- Role Dropdown (Make read-only if needed, or handle updates) ---
          Container(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.grey[50],
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.grey[300]!),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: _selectedRole,
                isExpanded: true,
                items: ['Admin', 'Family Member', 'Guest']
                    .map((String value) => DropdownMenuItem<String>(
                        value: value, child: Text(value)))
                    .toList(),
                onChanged: (newValue) {
                  if (newValue != null)
                    setState(() => _selectedRole = newValue);
                },
              ),
            ),
          ),
          SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Save / Cancel Buttons
              ElevatedButton.icon(
                onPressed: _isLoading || _isSaving || _isUploading
                    ? null
                    : _saveProfile,
                icon: _isSaving
                    ? SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation(Colors.white)))
                    : Icon(Icons.check, size: 16),
                label: Text('Save'),
                style: ElevatedButton.styleFrom(
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                ),
              ),
              SizedBox(width: 12),
              TextButton.icon(
                onPressed: _isLoading || _isSaving || _isUploading
                    ? null
                    : _toggleEditMode,
                icon: Icon(Icons.close, size: 16),
                label: Text('Cancel'),
                style: TextButton.styleFrom(
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  foregroundColor: Colors.grey[700],
                  backgroundColor: Colors.grey[100],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPersonalInfo() {
    // Shows Email, Phone etc. - Modify _buildInfoItem if needed
    return Container(
      decoration: BoxDecoration(
        /* Card Styling */ color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.secondaryWithOpacity(0.2)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.03),
            blurRadius: 10,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              children: [
                Text(
                  'Personal Information',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                    color: AppColors.primary,
                  ),
                ),
              ],
            ),
          ),
          Divider(height: 1, color: AppColors.divider),
          _buildInfoItem(
              icon: Icons.email_outlined,
              label: 'Email',
              controller: _emailController,
              keyboardType: TextInputType.emailAddress),
          Divider(height: 1, color: AppColors.divider),
          _buildInfoItem(
              icon: Icons.phone_outlined,
              label: 'Phone',
              controller: _phoneController,
              keyboardType: TextInputType.phone), // Now editable via controller
          Divider(height: 1, color: AppColors.divider),
          // Date Added (Non-editable)
          Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: AppColors.secondaryWithOpacity(0.2),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    Icons.calendar_today,
                    color: AppColors.primary,
                    size: 20,
                  ),
                ),
                SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Date Added',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.grey[600],
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        _dateAdded,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoItem({
    required IconData icon,
    required String label,
    required TextEditingController controller,
    TextInputType keyboardType = TextInputType.text,
  }) {
    // Builds individual rows in Personal Info section
    return Padding(
      padding: EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            /* Icon Styling */ width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AppColors.secondaryWithOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: Icon(
              icon,
              color: AppColors.primary,
              size: 20,
            ),
          ),
          SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 14,
                    color: Colors.grey[600],
                  ),
                ),
                SizedBox(height: 4),
                // Show TextField only in edit mode
                _isEditing
                    ? SizedBox(
                        height: 45,
                        child: TextField(
                          controller: controller,
                          keyboardType: keyboardType,
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w500),
                          decoration: InputDecoration(
                              contentPadding: EdgeInsets.symmetric(
                                  horizontal: 12, vertical: 8),
                              border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide:
                                      BorderSide(color: Colors.grey[300]!)),
                              enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide:
                                      BorderSide(color: Colors.grey[300]!)),
                              focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide:
                                      BorderSide(color: AppColors.primary)),
                              filled: true,
                              fillColor: Colors.grey[50]),
                        ),
                      )
                    : Text(
                        controller.text.isEmpty ? 'N/A' : controller.text,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // --- NEW Button to trigger password change dialog ---
  Widget _buildChangePasswordButton() {
    return GestureDetector(
      onTap: _showChangePasswordDialog,
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.secondaryWithOpacity(0.2)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.03),
              blurRadius: 10,
              offset: Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              // Icon and Text
              children: [
                Icon(
                  Icons.lock_outline,
                  color: AppColors.primary,
                  size: 20,
                ),
                SizedBox(width: 12),
                Text(
                  'Change Password',
                  style: TextStyle(
                    color: AppColors.primary,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            Icon(
              Icons.arrow_forward_ios,
              color: Colors.grey[400],
              size: 16,
            ),
          ],
        ),
      ),
    );
  }

  // Builds the logout button
  Widget _buildLogoutButton() {
    return GestureDetector(
      onTap: _isLoading || _isSaving || _isUploading
          ? null
          : _handleLogout, // Disable while busy
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.all(16),
        decoration: BoxDecoration(
          /* Logout Button Styling */ color: Colors.red[50],
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.red[100]!),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.logout,
              color: Colors.red[600],
              size: 20,
            ),
            SizedBox(width: 8),
            Text(
              'Logout',
              style: TextStyle(
                color: Colors.red[600],
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAuthenticatedImage(String? relativePath,
      {double? width, double? height, BoxFit fit = BoxFit.cover}) {
    if (relativePath == null ||
        relativePath.isEmpty ||
        relativePath == 'default_avatar.png') {
      return Center(
          child: Icon(Icons.person,
              size: (width ?? 100) * 0.6, color: Colors.grey[400]));
    }
    final key = ValueKey(relativePath); // Use key to help update state
    return FutureBuilder<Uint8List>(
      key: key,
      future: _apiService.getAuthenticatedImage(relativePath),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return Center(
              child: SizedBox(
                  width: 30,
                  height: 30,
                  child: CircularProgressIndicator(strokeWidth: 2)));
        } else if (snapshot.hasError) {
          print("Avatar Load Error: ${snapshot.error}");
          return Tooltip(
              message: snapshot.error
                  .toString()
                  .substring(0, min(snapshot.error.toString().length, 100)),
              child: Center(
                  child: Icon(Icons.error_outline,
                      size: (width ?? 100) * 0.5, color: Colors.red[300])));
        } else if (snapshot.hasData) {
          if (snapshot.data!.isEmpty)
            return Center(
                child: Icon(Icons.broken_image_outlined,
                    size: (width ?? 100) * 0.5, color: Colors.orange[300]));
          try {
            return Image.memory(
              snapshot.data!,
              width: width,
              height: height,
              fit: fit,
              gaplessPlayback: true,
              errorBuilder: (context, error, stackTrace) {
                print("Image.memory ERROR (Avatar): $error");
                return Center(
                    child: Icon(Icons.broken_image,
                        size: (width ?? 100) * 0.5, color: Colors.red[400]));
              },
            );
          } catch (e) {
            print("Image.memory EXCEPTION (Avatar): $e");
            return Center(
                child: Icon(Icons.broken_image,
                    size: (width ?? 100) * 0.5, color: Colors.purple[400]));
          }
        } else {
          return Center(
              child: Icon(Icons.person,
                  size: (width ?? 100) * 0.6, color: Colors.grey[400]));
        }
      },
    );
  }
} // End _ProfileScreenState

// --- NEW Separate Widget for Change Password Dialog ---
class ChangePasswordDialog extends StatefulWidget {
  final ApiService apiService;

  const ChangePasswordDialog({Key? key, required this.apiService})
      : super(key: key);

  @override
  _ChangePasswordDialogState createState() => _ChangePasswordDialogState();
}

class _ChangePasswordDialogState extends State<ChangePasswordDialog> {
  final _formKey = GlobalKey<FormState>();
  final _currentPasswordController = TextEditingController();
  final _newPasswordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  bool _isLoading = false;
  String? _errorMessage;
  bool _obscureCurrent = true;
  bool _obscureNew = true;
  bool _obscureConfirm = true;

  @override
  void dispose() {
    _currentPasswordController.dispose();
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _submitChangePassword() async {
    if (!_formKey.currentState!.validate()) return;
    if (_newPasswordController.text != _confirmPasswordController.text) {
      setState(() => _errorMessage = "New passwords do not match");
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      await widget.apiService.changePassword(
        _currentPasswordController.text,
        _newPasswordController.text,
      );
      if (!mounted) return;
      Navigator.of(context).pop(); // Close dialog on success
      ScaffoldMessenger.of(context).showSnackBar(
        // Show success on previous screen
        SnackBar(
            content: Text("Password updated successfully"),
            backgroundColor: Colors.green[600]),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.toString().replaceFirst('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text("Change Login Password"),
      contentPadding: EdgeInsets.fromLTRB(24, 20, 24, 0),
      content: Form(
        key: _formKey,
        child: SingleChildScrollView(
          // Allows scrolling if keyboard appears
          child: Column(
            mainAxisSize: MainAxisSize.min, // Make dialog height fit content
            children: <Widget>[
              if (_errorMessage != null)
                Container(
                  /* Error styling */ padding: EdgeInsets.all(8),
                  margin: EdgeInsets.only(bottom: 10),
                  color: Colors.red[50],
                  child: Text(
                    _errorMessage!,
                    style: TextStyle(color: Colors.red[700], fontSize: 13),
                    textAlign: TextAlign.center,
                  ),
                ),
              // Current Password
              TextFormField(
                controller: _currentPasswordController,
                obscureText: _obscureCurrent,
                decoration: InputDecoration(
                    labelText: 'Current Password',
                    isDense: true,
                    prefixIcon: Icon(Icons.lock_outline),
                    suffixIcon: IconButton(
                        icon: Icon(_obscureCurrent
                            ? Icons.visibility_outlined
                            : Icons.visibility_off_outlined),
                        onPressed: () => setState(
                            () => _obscureCurrent = !_obscureCurrent))),
                validator: (value) => value == null || value.isEmpty
                    ? 'Please enter current password'
                    : null,
              ),
              SizedBox(height: 16),
              // New Password
              TextFormField(
                  controller: _newPasswordController,
                  obscureText: _obscureNew,
                  decoration: InputDecoration(
                      labelText: 'New Password',
                      isDense: true,
                      prefixIcon: Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                          icon: Icon(_obscureNew
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined),
                          onPressed: () =>
                              setState(() => _obscureNew = !_obscureNew))),
                  validator: (value) {
                    if (value == null || value.isEmpty)
                      return 'Please enter new password';
                    if (value.length < 6)
                      return 'Password must be at least 6 characters';
                    return null;
                  }),
              SizedBox(height: 16),
              // Confirm New Password
              TextFormField(
                  controller: _confirmPasswordController,
                  obscureText: _obscureConfirm,
                  decoration: InputDecoration(
                      labelText: 'Confirm New Password',
                      isDense: true,
                      prefixIcon: Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                          icon: Icon(_obscureConfirm
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined),
                          onPressed: () => setState(
                              () => _obscureConfirm = !_obscureConfirm))),
                  validator: (value) {
                    if (value == null || value.isEmpty)
                      return 'Please confirm new password';
                    if (value != _newPasswordController.text)
                      return 'Passwords do not match';
                    return null;
                  }),
            ],
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          child: Text("Cancel"),
          onPressed: _isLoading ? null : () => Navigator.of(context).pop(),
        ),
        ElevatedButton(
          child: _isLoading
              ? SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : Text("Update Password"),
          onPressed: _isLoading ? null : _submitChangePassword,
        ),
      ],
    );
  }
}
