// lib/screens/users_screen.dart

import 'package:flutter/material.dart';
import 'package:neuralock/utils/app_colors.dart';
import 'package:neuralock/widgets/nav_bar.dart'; // Assuming NavBar exists
import 'package:image_picker/image_picker.dart';
import 'package:neuralock/services/api_service.dart';
import 'package:neuralock/models/user_model.dart'; // Import the User model
import 'dart:io'; // For File type
import 'dart:typed_data'; // Import Uint8List
import 'dart:math'; // For min function in debug text

class UsersScreen extends StatefulWidget {
  @override
  _UsersScreenState createState() => _UsersScreenState();
}

class _UsersScreenState extends State<UsersScreen> {
  List<User> _users = []; // List to hold fetched users
  bool _isLoading = true; // For general loading states
  bool _isActionLoading = false; // For specific actions like add/delete/upload
  String? _expandedUserId; // Track which user detail is expanded
  bool _showAddModal = false; // Control visibility of the add user modal

  // Controllers for the "Add User" modal form
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  String _selectedRole = "Family Member"; // Default role for new user
  List<File> _newUserImageFiles = []; // Store picked File objects for new user

  final _imagePicker = ImagePicker(); // Instance for picking images
  final ApiService _apiService = ApiService(); // Instance of your API service

  @override
  void initState() {
    super.initState();
    _loadUsers(); // Load users when the screen initializes
  }

  @override
  void dispose() {
    // Dispose text controllers
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  // --- Data Fetching and Actions ---

  Future<void> _loadUsers() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
    });
    try {
      final usersData = await _apiService.getUsers();
      if (!mounted) return;
      setState(() {
        _users = usersData.map((userData) => User.fromJson(userData)).toList();
      });
    } catch (e) {
      if (!mounted) return;
      _showErrorSnackbar(
          "Error loading users: ${e.toString().replaceFirst('Exception: ', '')}");
    } finally {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });
    }
  }

  void _toggleUserExpand(String userId) {
    setState(() {
      _expandedUserId = (_expandedUserId == userId) ? null : userId;
    });
  }

  Future<void> _pickAndUploadImage(String userId) async {
    if (_isActionLoading) return;
    try {
      final XFile? pickedFile = await _imagePicker.pickImage(
          source: ImageSource.gallery, imageQuality: 80);
      if (pickedFile == null || !mounted) return;
      setState(() {
        _isActionLoading = true;
      });
      await _apiService.uploadUserImage(userId, File(pickedFile.path));
      if (!mounted) return;
      _showSuccessSnackbar('Image uploaded successfully');
      await _loadUsers();
    } catch (e) {
      if (!mounted) return;
      _showErrorSnackbar(
          "Error uploading image: ${e.toString().replaceFirst('Exception: ', '')}");
    } finally {
      if (!mounted) return;
      setState(() {
        _isActionLoading = false;
      });
    }
  }

  Future<void> _showUserImages(String userId, String userName) async {
    if (_isActionLoading) return;
    setState(() {
      _isActionLoading = true;
    });
    List<dynamic> images = [];
    try {
      images = await _apiService.getUserImages(userId);
      if (!mounted) return;
      setState(() {
        _isActionLoading = false;
      });
      if (images.isEmpty) {
        _showInfoSnackbar('No face images found for this user');
        return;
      }
      showDialog(
        context: context,
        builder: (dialogContext) => UserImagesDialog(
          // Use the separate dialog widget
          userId: userId,
          userName: userName,
          images: images,
          apiService: _apiService,
          onActionComplete: () {
            Navigator.of(dialogContext).pop();
            _loadUsers();
          },
          onError: (message) {
            _showErrorSnackbar(message);
          },
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isActionLoading = false;
      });
      _showErrorSnackbar(
          "Error loading images: ${e.toString().replaceFirst('Exception: ', '')}");
    }
  }

  Future<void> _addUser() async {
    if (_nameController.text.isEmpty ||
        _emailController.text.isEmpty ||
        _passwordController.text.isEmpty) {
      _showErrorSnackbar('Please fill in name, email, and password');
      return;
    }
    if (_newUserImageFiles.isEmpty) {
      _showErrorSnackbar('Please upload at least one face image');
      return;
    }
    if (_isActionLoading) return;
    setState(() {
      _isActionLoading = true;
    });
    try {
      final userData = {
        'name': _nameController.text,
        'email': _emailController.text,
        'password': _passwordController.text,
        'role': _selectedRole,
      };
      final newUser = await _apiService.createUser(userData);
      final newUserId = newUser['id'];
      await Future.wait(_newUserImageFiles
          .map((imageFile) => _apiService.uploadUserImage(newUserId, imageFile))
          .toList());
      if (!mounted) return;
      setState(() {
        _showAddModal = false;
        _nameController.clear();
        _emailController.clear();
        _passwordController.clear();
        _selectedRole = "Family Member";
        _newUserImageFiles = [];
      });
      _showSuccessSnackbar('User added successfully');
      await _loadUsers();
    } catch (e) {
      if (!mounted) return;
      _showErrorSnackbar(
          "Error adding user: ${e.toString().replaceFirst('Exception: ', '')}");
    } finally {
      if (!mounted) return;
      setState(() {
        _isActionLoading = false;
      });
    }
  }

  Future<void> _deleteUser(String userId) async {
    if (_isActionLoading) return;
    setState(() {
      _isActionLoading = true;
    });
    try {
      await _apiService.deleteUser(userId);
      if (!mounted) return;
      _showSuccessSnackbar('User deleted successfully');
      if (_expandedUserId == userId) {
        _expandedUserId = null;
      }
      await _loadUsers();
    } catch (e) {
      if (!mounted) return;
      _showErrorSnackbar(
          "Error deleting user: ${e.toString().replaceFirst('Exception: ', '')}");
    } finally {
      if (!mounted) return;
      setState(() {
        _isActionLoading = false;
      });
    }
  }

  Future<void> _confirmDeleteUser(String userId, String userName) async {
    return showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: Text('Delete User'),
        content: Text(
            'Are you sure you want to permanently delete user "$userName" and all associated face data?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              _deleteUser(userId);
            },
            child: Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
  }

  Future<void> _pickImageForNewUser() async {
    try {
      final XFile? pickedFile = await _imagePicker.pickImage(
          source: ImageSource.gallery, imageQuality: 80);
      if (pickedFile == null || !mounted) return;
      _newUserImageFiles.add(File(pickedFile.path));
      // Need modalSetState to update the preview list inside the modal
    } catch (e) {
      _showErrorSnackbar(
          "Error picking image: ${e.toString().replaceFirst('Exception: ', '')}");
    }
  }

  void _removeNewUserImage(int index) {
    // Need modalSetState to update the preview list inside the modal
    _newUserImageFiles.removeAt(index);
  }

  // --- Helper UI Methods ---
  void _showErrorSnackbar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red[600]),
    );
  }

  void _showSuccessSnackbar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.green[600]),
    );
  }

  void _showInfoSnackbar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  // --- Build Methods ---

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Column(
            children: [
              _buildAppBar(),
              Expanded(
                child: _isLoading && _users.isEmpty
                    ? Center(child: CircularProgressIndicator())
                    : RefreshIndicator(
                        onRefresh: _loadUsers,
                        child: _users.isEmpty && !_isLoading
                            ? _buildEmptyUsersList()
                            : ListView(
                                physics: AlwaysScrollableScrollPhysics(),
                                padding: EdgeInsets.all(16),
                                children: [
                                  _buildAddUserButton(),
                                  SizedBox(height: 16),
                                  _buildUsersListContainer(),
                                  SizedBox(height: 80),
                                ],
                              ),
                      ),
              ),
            ],
          ),
          if (_showAddModal) _buildAddUserModal(),
          if (_isActionLoading)
            Container(
              color: Colors.black.withOpacity(0.3),
              child: Center(
                child: CircularProgressIndicator(),
              ),
            ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: NavBar(currentIndex: 2),
          ),
        ],
      ),
    );
  }

  Widget _buildAppBar() {
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
            onTap: () => Navigator.pushNamed(context, '/profile'),
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: AppColors.secondaryWithOpacity(0.3),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Icon(
                Icons.person_outline,
                color: Colors.white,
                size: 20,
              ),
            ),
          ),
          Text(
            'Manage Users',
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

  Widget _buildAddUserButton() {
    // TODO: Implement role check from app state if needed
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton.icon(
        onPressed: () => setState(() {
          _showAddModal = true;
        }),
        icon: Icon(Icons.add),
        label: Text('Add New User'),
      ),
    );
  }

  Widget _buildUsersListContainer() {
    return Container(
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
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Authorized Users',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                    color: AppColors.primary,
                  ),
                ),
                Container(
                  padding: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.secondaryWithOpacity(0.2),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    '${_users.length} Users',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.primary,
                    ),
                  ),
                ),
              ],
            ),
          ),
          Divider(height: 1, color: AppColors.divider),
          ListView.separated(
            shrinkWrap: true,
            physics: NeverScrollableScrollPhysics(),
            itemCount: _users.length,
            separatorBuilder: (context, index) =>
                Divider(height: 1, color: AppColors.divider),
            itemBuilder: (context, index) {
              final user = _users[index];
              return Column(
                children: [
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    child: Row(
                      children: [
                        // --- Use Authenticated Image Helper for Avatar ---
                        Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: AppColors.secondaryWithOpacity(0.3),
                              ),
                            ),
                            child: ClipRRect(
                                borderRadius: BorderRadius.circular(24),
                                child: _buildAuthenticatedImage(
                                    user.avatar) // Use helper
                                )),
                        // --------------------------------------------
                        SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                user.name,
                                style: TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: Colors.grey[800],
                                ),
                              ),
                              SizedBox(height: 4),
                              Text(
                                '${user.role} • Added ${user.dateAdded.split('T')[0]}',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Colors.grey[500],
                                ),
                              ),
                            ],
                          ),
                        ),
                        Row(
                          children: [
                            IconButton(
                              iconSize: 20,
                              visualDensity: VisualDensity.compact,
                              onPressed: () => _toggleUserExpand(user.id),
                              icon: Icon(
                                _expandedUserId == user.id
                                    ? Icons.keyboard_arrow_up
                                    : Icons.keyboard_arrow_down,
                                color: AppColors.primary,
                              ),
                            ),
                            // TODO: Add role check here to hide delete for non-admins
                            IconButton(
                              iconSize: 20,
                              visualDensity: VisualDensity.compact,
                              onPressed: () =>
                                  _confirmDeleteUser(user.id, user.name),
                              icon: Icon(
                                Icons.delete_outline,
                                color: Colors.red[500],
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  if (_expandedUserId == user.id) _buildUserDetail(user),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildUserDetail(User user) {
    // TODO: Add role check for upload button visibility
    // bool isAdmin = ...; bool isSelf = currentUser.id == user.id;
    return Container(
      color: Colors.grey[50],
      padding: EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.email_outlined, size: 16, color: Colors.grey[600]),
              SizedBox(width: 8),
              Text(
                user.email,
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey[700],
                ),
              ),
            ],
          ),
          SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Face Images',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                  color: Colors.grey[700],
                ),
              ),
              TextButton.icon(
                onPressed: () => _showUserImages(user.id, user.name),
                icon: Icon(Icons.photo_library, size: 16),
                label: Text('View/Manage'),
                style: TextButton.styleFrom(
                    padding: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    foregroundColor: AppColors.primary),
              ),
            ],
          ),
          SizedBox(height: 4),
          // if (isAdmin || isSelf) // Conditionally show upload button
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: () => _pickAndUploadImage(user.id),
              icon: Icon(Icons.add_a_photo, size: 16),
              label: Text('Upload New Face Image'),
              style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.secondary,
                  foregroundColor: Colors.white,
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  elevation: 1,
                  textStyle: TextStyle(fontSize: 13)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyUsersList() {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: 48),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.people_outline,
              size: 64,
              color: Colors.grey[300],
            ),
            SizedBox(height: 16),
            Text(
              'No users found',
              style: TextStyle(
                  color: Colors.grey[600],
                  fontSize: 18,
                  fontWeight: FontWeight.w500),
            ),
            SizedBox(height: 8),
            Text(
              'Click "Add New User" to get started.',
              style: TextStyle(
                color: Colors.grey[400],
                fontSize: 14,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAddUserModal() {
    // Use StatefulBuilder for modal-specific state (image previews)
    return StatefulBuilder(builder: (modalContext, modalSetState) {
      return Positioned.fill(
        child: Material(
          // Add Material widget for correct theme inheritance
          color: Colors.black.withOpacity(0.6),
          child: Center(
            child: Container(
              width: MediaQuery.of(context).size.width * 0.9,
              constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(context).size.height * 0.85),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Modal Header
                  Padding(
                    padding: EdgeInsets.fromLTRB(16, 16, 8, 16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Add New User',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w600,
                            color: AppColors.primary,
                          ),
                        ),
                        IconButton(
                          visualDensity: VisualDensity.compact,
                          onPressed: () {
                            setState(() {
                              _showAddModal = false;
                              _nameController.clear();
                              _emailController.clear();
                              _passwordController.clear();
                              _selectedRole = "Family Member";
                              _newUserImageFiles = [];
                            });
                          },
                          icon: Icon(Icons.close),
                          color: Colors.grey[500],
                        ),
                      ],
                    ),
                  ),
                  Divider(height: 1, color: AppColors.divider),
                  // Scrollable Form
                  Flexible(
                    child: SingleChildScrollView(
                      padding: EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          _buildModalTextField(
                              label: 'Name *',
                              controller: _nameController,
                              hint: 'Enter user name'),
                          _buildModalTextField(
                              label: 'Email *',
                              controller: _emailController,
                              hint: 'Enter email address',
                              keyboardType: TextInputType.emailAddress),
                          _buildModalTextField(
                              label: 'Password *',
                              controller: _passwordController,
                              hint: 'Enter password',
                              obscureText: true),
                          _buildModalDropdown(
                              label: 'Role',
                              value: _selectedRole,
                              items: ['Admin', 'Family Member', 'Guest'],
                              onChanged: (val) => modalSetState(() =>
                                  _selectedRole = val!)), // Use modalSetState
                          SizedBox(height: 16),
                          Text(
                            'Face Images *',
                            style: TextStyle(
                              fontWeight: FontWeight.w500,
                              color: Colors.grey[700],
                            ),
                          ),
                          SizedBox(height: 4),
                          Text(
                            'Add at least one clear face image',
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.grey[500],
                            ),
                          ),
                          SizedBox(height: 8),
                          // Image Upload/Preview Area
                          Container(
                            child: Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                ..._newUserImageFiles
                                    .asMap()
                                    .entries
                                    .map((entry) {
                                  final index = entry.key;
                                  final imageFile = entry.value;
                                  return Stack(
                                    children: [
                                      Container(
                                          width: 80,
                                          height: 80,
                                          decoration: BoxDecoration(
                                            borderRadius:
                                                BorderRadius.circular(8),
                                            border: Border.all(
                                                color: Colors.grey[300]!),
                                          ),
                                          child: ClipRRect(
                                              borderRadius:
                                                  BorderRadius.circular(7),
                                              child: Image.file(imageFile,
                                                  fit: BoxFit.cover,
                                                  errorBuilder: (c, e, s) =>
                                                      Center(
                                                          child: Icon(
                                                              Icons.person,
                                                              size: 40,
                                                              color:
                                                                  Colors.grey[
                                                                      400]))))),
                                      Positioned(
                                        top: -12,
                                        right: -12,
                                        child: IconButton(
                                          visualDensity: VisualDensity.compact,
                                          padding: EdgeInsets.zero,
                                          onPressed: () => modalSetState(
                                              () => _removeNewUserImage(index)),
                                          icon: Container(
                                              padding: EdgeInsets.all(2),
                                              decoration: BoxDecoration(
                                                color: Colors.red[600]
                                                    ?.withOpacity(0.8),
                                                shape: BoxShape.circle,
                                              ),
                                              child: Icon(
                                                Icons.close,
                                                size: 14,
                                                color: Colors.white,
                                              )),
                                        ),
                                      ),
                                    ],
                                  );
                                }),
                                GestureDetector(
                                  onTap: () async {
                                    await _pickImageForNewUser();
                                    modalSetState(() {});
                                  },
                                  child: Container(
                                    width: 80,
                                    height: 80,
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(
                                        color:
                                            AppColors.secondaryWithOpacity(0.4),
                                        width: 2,
                                        style: BorderStyle.solid,
                                      ),
                                    ),
                                    child: Column(
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        Icon(
                                          Icons.add_a_photo_outlined,
                                          color: AppColors.primary,
                                          size: 24,
                                        ),
                                        SizedBox(height: 4),
                                        Text(
                                          'Upload',
                                          style: TextStyle(
                                            fontSize: 12,
                                            color: AppColors.primary,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  // Modal Footer/Actions
                  Divider(height: 1, color: AppColors.divider),
                  Padding(
                    padding: EdgeInsets.all(16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        TextButton(
                          onPressed: () {
                            setState(() {
                              _showAddModal = false;
                              _nameController.clear();
                              _emailController.clear();
                              _passwordController.clear();
                              _selectedRole = "Family Member";
                              _newUserImageFiles = [];
                            });
                          },
                          child: Text('Cancel'),
                        ),
                        SizedBox(width: 8),
                        ElevatedButton(
                          onPressed: _addUser,
                          child: Text('Add User'),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    });
  }

  // Helper for TextFields in the modal
  Widget _buildModalTextField(
      {required String label,
      required TextEditingController controller,
      String? hint,
      bool obscureText = false,
      TextInputType? keyboardType}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontWeight: FontWeight.w500,
            color: Colors.grey[700],
          ),
        ),
        SizedBox(height: 8),
        TextField(
          controller: controller,
          obscureText: obscureText,
          keyboardType: keyboardType,
          decoration: InputDecoration(hintText: hint, isDense: true),
        ),
        SizedBox(height: 16),
      ],
    );
  }

  // Helper for Dropdown in the modal
  Widget _buildModalDropdown(
      {required String label,
      required String value,
      required List<String> items,
      required ValueChanged<String?> onChanged}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontWeight: FontWeight.w500,
            color: Colors.grey[700],
          ),
        ),
        SizedBox(height: 8),
        Container(
          padding: EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: Colors.grey[50],
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.grey[300]!),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              isExpanded: true,
              value: value,
              items: items
                  .map((String val) =>
                      DropdownMenuItem<String>(value: val, child: Text(val)))
                  .toList(),
              onChanged: onChanged,
            ),
          ),
        ),
        SizedBox(height: 16),
      ],
    );
  }

  // --- Helper Widget to display authenticated images ---
  Widget _buildAuthenticatedImage(String? relativePath,
      {double? width, double? height, BoxFit fit = BoxFit.cover}) {
    if (relativePath == null ||
        relativePath.isEmpty ||
        relativePath == 'default_avatar.png') {
      return Center(
          child: Icon(Icons.person,
              size: (width ?? 48) * 0.6, color: Colors.grey[400]));
    }
    // Use a unique key based on the path to potentially help with rebuilds
    final key = ValueKey(relativePath);

    return FutureBuilder<Uint8List>(
      key: key, // Add key here
      future: _apiService.getAuthenticatedImage(relativePath),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return Center(
              child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2)));
        } else if (snapshot.hasError) {
          // Display error from snapshot for debugging
          return Tooltip(
            // Show error on hover/long press (web/desktop)
            message: snapshot.error.toString(),
            child: Center(
                child: Icon(Icons.error_outline,
                    size: (width ?? 48) * 0.5, color: Colors.red[300])),
          );
        } else if (snapshot.hasData) {
          if (snapshot.data!.isEmpty) {
            return Center(
                child: Icon(Icons.broken_image_outlined,
                    size: (width ?? 48) * 0.5, color: Colors.orange[300]));
          }
          try {
            return Image.memory(
              snapshot.data!,
              width: width,
              height: height,
              fit: fit,
              gaplessPlayback: true,
              errorBuilder: (context, error, stackTrace) {
                print("Image.memory ERROR for $relativePath: $error");
                return Center(
                    child: Icon(Icons.broken_image,
                        size: (width ?? 48) * 0.5, color: Colors.red[400]));
              },
            );
          } catch (e) {
            print("Image.memory EXCEPTION for $relativePath: $e");
            return Center(
                child: Icon(Icons.broken_image,
                    size: (width ?? 48) * 0.5, color: Colors.purple[400]));
          }
        } else {
          return Center(
              child: Icon(Icons.person,
                  size: (width ?? 48) * 0.6, color: Colors.grey[400]));
        }
      },
    );
  }
} // End _UsersScreenState

// --- Separate StatefulWidget for the User Images Dialog ---
class UserImagesDialog extends StatefulWidget {
  final String userId;
  final String userName;
  final List<dynamic> images;
  final ApiService apiService;
  final VoidCallback onActionComplete;
  final Function(String) onError;

  const UserImagesDialog({
    Key? key,
    required this.userId,
    required this.userName,
    required this.images,
    required this.apiService,
    required this.onActionComplete,
    required this.onError,
  }) : super(key: key);

  @override
  _UserImagesDialogState createState() => _UserImagesDialogState();
}

class _UserImagesDialogState extends State<UserImagesDialog> {
  bool _isDialogLoading = false;
  late List<dynamic> _currentImages;

  @override
  void initState() {
    super.initState();
    _currentImages = List.from(widget.images);
  }

  Future<void> _setAvatar(String filename) async {
    if (_isDialogLoading) return;
    setState(() {
      _isDialogLoading = true;
    });
    try {
      await widget.apiService.setProfileImage(widget.userId, filename);
      widget.onActionComplete();
    } catch (e) {
      if (mounted) {
        setState(() {
          _isDialogLoading = false;
        });
        widget.onError(
            "Error setting avatar: ${e.toString().replaceFirst('Exception: ', '')}");
      }
    }
  }

  Future<void> _deleteImage(String filename) async {
    if (_isDialogLoading) return;
    bool? confirmDelete = await showDialog<bool>(
        context: context,
        builder: (BuildContext ctx) {
          return AlertDialog(
            title: Text("Delete Image?"),
            content: Text(
                "Are you sure you want to delete this face image? This cannot be undone."),
            actions: <Widget>[
              TextButton(
                  child: Text("Cancel"),
                  onPressed: () => Navigator.of(ctx).pop(false)),
              TextButton(
                  child: Text("Delete", style: TextStyle(color: Colors.red)),
                  onPressed: () => Navigator.of(ctx).pop(true)),
            ],
          );
        });
    if (confirmDelete != true || !mounted) return;

    setState(() {
      _isDialogLoading = true;
    });
    try {
      await widget.apiService.deleteUserImage(widget.userId, filename);
      if (mounted) {
        setState(() {
          _currentImages.removeWhere((img) => img['filename'] == filename);
          _isDialogLoading = false;
        });
      }
      widget.onError('Image deleted'); // Use callback for success message
    } catch (e) {
      if (mounted) {
        setState(() {
          _isDialogLoading = false;
        });
        widget.onError(
            "Error deleting image: ${e.toString().replaceFirst('Exception: ', '')}");
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('${widget.userName}\'s Images'),
      contentPadding: EdgeInsets.fromLTRB(16, 20, 16, 0),
      content: Container(
        width: double.maxFinite,
        constraints:
            BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.5),
        child: _isDialogLoading
            ? Center(child: CircularProgressIndicator())
            : _currentImages.isEmpty
                ? Center(child: Text("No images found."))
                : GridView.builder(
                    shrinkWrap: true,
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3,
                      crossAxisSpacing: 8,
                      mainAxisSpacing: 8,
                    ),
                    itemCount: _currentImages.length,
                    itemBuilder: (context, index) {
                      final image = _currentImages[index];
                      final relativePath = image['path'] ?? '';
                      final filename = image['filename'] ?? '';

                      return GestureDetector(
                        onTap: () => _setAvatar(filename),
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            ClipRRect(
                                borderRadius: BorderRadius.circular(4.0),
                                child: _buildAuthenticatedImageDialog(
                                    widget.apiService,
                                    relativePath) // Use helper
                                ),
                            Positioned(
                              top: 0,
                              right: 0,
                              child: GestureDetector(
                                onTap: () => _deleteImage(filename),
                                child: Container(
                                  padding: EdgeInsets.all(2),
                                  decoration: BoxDecoration(
                                    color: Colors.red.withOpacity(0.8),
                                    shape: BoxShape.circle,
                                  ),
                                  child: Icon(Icons.close,
                                      size: 14, color: Colors.white),
                                ),
                              ),
                            ),
                            Align(
                              alignment: Alignment.bottomCenter,
                              child: Container(
                                width: double.infinity,
                                color: Colors.black.withOpacity(0.4),
                                padding: EdgeInsets.symmetric(vertical: 2),
                                child: Text(
                                  "Set Avatar",
                                  style: TextStyle(
                                      color: Colors.white, fontSize: 8),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text('Close'),
        ),
      ],
    );
  }

  // Helper specifically for the dialog's images (Could be merged with screen's helper)
  Widget _buildAuthenticatedImageDialog(
      ApiService apiService, String? relativePath) {
    if (relativePath == null || relativePath.isEmpty) {
      return Container(
          color: Colors.grey[200],
          child: Icon(Icons.person, color: Colors.grey[400]));
    }
    return FutureBuilder<Uint8List>(
      future: apiService.getAuthenticatedImage(relativePath),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return Center(
              child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 1)));
        } else if (snapshot.hasError) {
          return Tooltip(
              message: snapshot.error.toString(),
              child: Container(
                  color: Colors.grey[200],
                  child: Icon(Icons.error_outline, color: Colors.grey[400])));
        } else if (snapshot.hasData) {
          if (snapshot.data!.isEmpty)
            return Center(child: Icon(Icons.broken_image_outlined));
          return Image.memory(snapshot.data!,
              fit: BoxFit.cover,
              gaplessPlayback: true,
              errorBuilder: (c, e, s) =>
                  Center(child: Icon(Icons.broken_image)));
        } else {
          return Container(
              color: Colors.grey[200],
              child: Icon(Icons.person, color: Colors.grey[400]));
        }
      },
    );
  }
} // End _UserImagesDialogState
