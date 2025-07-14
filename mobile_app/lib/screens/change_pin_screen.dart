// lib/screens/change_pin_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:neuralock/utils/app_colors.dart';
import 'package:neuralock/services/api_service.dart'; // Import ApiService

class ChangePinScreen extends StatefulWidget {
  @override
  _ChangePinScreenState createState() => _ChangePinScreenState();
}

class _ChangePinScreenState extends State<ChangePinScreen> {
  // Controllers for PIN digits
  final List<TextEditingController> _currentPinControllers =
      List.generate(6, (index) => TextEditingController());
  final List<TextEditingController> _newPinControllers =
      List.generate(6, (index) => TextEditingController());
  final List<TextEditingController> _confirmPinControllers =
      List.generate(6, (index) => TextEditingController());

  // Focus nodes for auto-focusing next field
  final List<FocusNode> _currentPinFocusNodes =
      List.generate(6, (index) => FocusNode());
  final List<FocusNode> _newPinFocusNodes =
      List.generate(6, (index) => FocusNode());
  final List<FocusNode> _confirmPinFocusNodes =
      List.generate(6, (index) => FocusNode());

  // State variables
  String _step = 'current'; // 'current', 'new', 'confirm', 'success'
  String? _errorMessage;
  bool _isLoading = false; // For loading indicator on buttons
  bool _isPinCurrentlySet = true; // Assume set initially, check in initState

  final ApiService _apiService = ApiService(); // Instance of your API service

  @override
  void initState() {
    super.initState();
    _checkInitialPinStatus(); // Check if a PIN exists on the server

    // Add listeners for auto-focusing logic
    _setupPinListeners(_currentPinControllers, _currentPinFocusNodes);
    _setupPinListeners(_newPinControllers, _newPinFocusNodes);
    _setupPinListeners(_confirmPinControllers, _confirmPinFocusNodes);
  }

  // Helper to set up listeners for a set of PIN fields
  void _setupPinListeners(
      List<TextEditingController> controllers, List<FocusNode> focusNodes) {
    for (int i = 0; i < 6; i++) {
      controllers[i].addListener(() {
        // Move focus forward on entry
        if (controllers[i].text.length == 1 && i < 5) {
          FocusScope.of(context).requestFocus(focusNodes[i + 1]);
        }
        // Optional: Move focus backward on delete (already handled in onChanged)
      });
    }
  }

  // Check if a global PIN is already set when screen loads
  Future<void> _checkInitialPinStatus() async {
    setState(() {
      _isLoading = true;
    }); // Show loading initially
    try {
      _isPinCurrentlySet = await _apiService.getGlobalPinStatus();
      // If no PIN is set, skip the 'current' step
      if (!_isPinCurrentlySet) {
        setState(() {
          _step = 'new';
        });
        print("No global PIN set, starting with new PIN creation.");
      } else {
        print("Global PIN is set, starting with current PIN verification.");
      }
    } catch (e) {
      print("Error checking PIN status: $e");
      // Assume PIN is set if status check fails to avoid locking user out
      // Or display an error message
      setState(() {
        _errorMessage = "Could not check PIN status. Please try again.";
        // Keep step as 'current' assuming one exists
        _isPinCurrentlySet = true;
      });
    } finally {
      // Ensure loading is stopped even if check fails
      if (mounted) {
        // Check if the widget is still in the tree
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    // Dispose all controllers and focus nodes
    for (var controller in _currentPinControllers) controller.dispose();
    for (var controller in _newPinControllers) controller.dispose();
    for (var controller in _confirmPinControllers) controller.dispose();
    for (var node in _currentPinFocusNodes) node.dispose();
    for (var node in _newPinFocusNodes) node.dispose();
    for (var node in _confirmPinFocusNodes) node.dispose();
    super.dispose();
  }

  // Handles the logic when the 'Continue' or 'Update PIN' button is pressed
  Future<void> _handleContinue() async {
    setState(() {
      _errorMessage = null;
      _isLoading = true;
    }); // Start loading

    try {
      // --- Step 1: Verify Current PIN (if one is set) ---
      if (_step == 'current' && _isPinCurrentlySet) {
        bool isCurrentComplete =
            _currentPinControllers.every((c) => c.text.isNotEmpty);
        if (!isCurrentComplete)
          throw Exception('Please enter the current 6-digit Global PIN');
        String currentPin = _currentPinControllers.map((c) => c.text).join();
        if (currentPin.length != 6)
          throw Exception('Current PIN must be 6 digits');

        // Call API to verify
        bool verified = await _apiService.verifyGlobalPin(currentPin);
        if (!verified) throw Exception('Incorrect current Global PIN');

        // Verification successful, move to next step
        setState(() {
          _step = 'new';
        });
        _clearControllers(_currentPinControllers); // Clear current PIN fields

        // --- Step 2: Enter New PIN ---
        // Logic handles skipping here if !_isPinCurrentlySet was true initially
      } else if (_step == 'new') {
        bool isNewComplete = _newPinControllers.every((c) => c.text.isNotEmpty);
        if (!isNewComplete)
          throw Exception('Please enter a complete 6-digit new PIN');
        String newPin = _newPinControllers.map((c) => c.text).join();
        if (newPin.length != 6) throw Exception('New PIN must be 6 digits');

        // New PIN entered, move to confirmation step
        setState(() {
          _step = 'confirm';
        });

        // --- Step 3: Confirm New PIN & Update ---
      } else if (_step == 'confirm') {
        bool isConfirmComplete =
            _confirmPinControllers.every((c) => c.text.isNotEmpty);
        if (!isConfirmComplete)
          throw Exception('Please confirm your new 6-digit PIN');

        String newPin = _newPinControllers.map((c) => c.text).join();
        String confirmPin = _confirmPinControllers.map((c) => c.text).join();

        if (newPin.length != 6)
          throw Exception(
              'New PIN must be 6 digits'); // Redundant check, good practice
        if (newPin != confirmPin) throw Exception('PINs do not match');

        // PINs match, call API to update
        await _apiService.updateGlobalPin(newPin);

        // Update successful, move to success screen
        setState(() {
          _step = 'success';
          _isPinCurrentlySet = true;
        }); // Mark as set now
        _clearControllers(_newPinControllers);
        _clearControllers(_confirmPinControllers);
      }
    } catch (e) {
      // Display error message from API or validation
      setState(() {
        _errorMessage = e.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      // Ensure loading indicator stops regardless of outcome
      if (mounted) {
        // Check if widget is still mounted before calling setState
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // Helper to clear controllers
  void _clearControllers(List<TextEditingController> controllers) {
    for (var controller in controllers) {
      controller.clear();
    }
    // Optionally reset focus to the first field of the next step
  }

  // --- Build Methods ---

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _buildAppBar(), // Build the custom app bar
          Expanded(
            child: SingleChildScrollView(
              padding: EdgeInsets.all(16),
              // Show success message or PIN entry content based on current step
              child: _step == 'success'
                  ? _buildSuccessContent()
                  : _buildPinContent(),
            ),
          ),
        ],
      ),
    );
  }

  // Builds the top app bar with back button and title
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
            // Back button
            onTap: () => Navigator.pop(context),
            child: Container(
              /* Back button styling */ width: 40,
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
            'Change Keypad PIN', // Updated title
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(width: 40), // Spacer for centering title
        ],
      ),
    );
  }

  // Builds the main content area for PIN entry steps
  Widget _buildPinContent() {
    // Determine titles and subtitles based on the current step and if a PIN is already set
    bool showCurrentPinStep = _isPinCurrentlySet && _step == 'current';
    String title = showCurrentPinStep
        ? 'Enter Current Keypad PIN'
        : _step == 'new'
            ? 'Create New Keypad PIN'
            : 'Confirm New Keypad PIN';
    String subtitle = showCurrentPinStep
        ? 'Please enter the current global PIN to continue'
        : _step == 'new'
            ? 'Choose a secure 6-digit PIN for the keypad'
            : 'Re-enter your new PIN to confirm';

    return Container(
      decoration: BoxDecoration(
        // Card styling
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
          // Card Header
          Container(
            /* Header styling */ padding: EdgeInsets.all(16),
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
            child: Row(
              children: [
                Container(
                  padding: EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.secondaryWithOpacity(0.3),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Icon(
                    Icons.vpn_key,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Keypad Security PIN',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                    Text(
                      'Update the global keypad access code',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.secondary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          // PIN Entry Section
          Padding(
            padding: EdgeInsets.all(24),
            child: Column(
              children: [
                Text(
                  title,
                  style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary),
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: 8),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: 14,
                    color: Colors.grey[600],
                  ),
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: 20),

                // --- Conditionally Display PIN Input Rows ---
                if (showCurrentPinStep)
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(
                        6,
                        (index) => _buildPinBox(index, _currentPinControllers,
                            _currentPinFocusNodes)),
                  ),
                // Always show New/Confirm when in those steps
                if (_step == 'new')
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(
                        6,
                        (index) => _buildPinBox(
                            index, _newPinControllers, _newPinFocusNodes)),
                  ),
                if (_step == 'confirm')
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(
                        6,
                        (index) => _buildPinBox(index, _confirmPinControllers,
                            _confirmPinFocusNodes)),
                  ),
                // ------------------------------------------

                // Error Message Area
                if (_errorMessage != null)
                  Container(
                    /* Error Box Styling */ margin: EdgeInsets.only(top: 16),
                    padding: EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.red[50],
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.red[100]!),
                    ),
                    child: Text(
                      _errorMessage!,
                      style: TextStyle(color: Colors.red[700]),
                      textAlign: TextAlign.center,
                    ),
                  ),

                SizedBox(height: 24),

                // Continue/Update Button
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _isLoading
                        ? null
                        : _handleContinue, // Disable when loading
                    child: _isLoading
                        ? SizedBox(
                            // Show loading spinner
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(
                                strokeWidth: 2,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                    Colors.white)))
                        : Text(_step == 'confirm'
                            ? 'Update PIN'
                            : 'Continue'), // Change button text
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // Helper widget to build individual PIN input boxes
  Widget _buildPinBox(int index, List<TextEditingController> controllers,
      List<FocusNode> focusNodes) {
    return Container(
      width: 40,
      height: 56,
      margin: EdgeInsets.symmetric(horizontal: 4),
      child: TextField(
        controller: controllers[index],
        focusNode: focusNodes[index],
        textAlign: TextAlign.center,
        keyboardType: TextInputType.number,
        maxLength: 1, // Only one digit per box
        obscureText: true, // Hide PIN digits
        style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        decoration: InputDecoration(
          counterText: '', // Hide the counter
          contentPadding: EdgeInsets.zero, // Center digit vertically
          border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(
                  color: AppColors.secondaryWithOpacity(0.4), width: 2)),
          enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(
                  color: AppColors.secondaryWithOpacity(0.4), width: 2)),
          focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: AppColors.secondary, width: 2)),
          filled: true,
          fillColor: Colors.grey[50],
        ),
        inputFormatters: [
          FilteringTextInputFormatter.digitsOnly
        ], // Only allow digits
        onChanged: (value) {
          // Move focus backward on delete if field is empty
          if (value.isEmpty && index > 0) {
            FocusScope.of(context).requestFocus(focusNodes[index - 1]);
          }
          // Move focus forward handled by listeners in initState
        },
      ),
    );
  }

  // Builds the success message display
  Widget _buildSuccessContent() {
    return Container(
      height:
          MediaQuery.of(context).size.height * 0.6, // Adjust height as needed
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
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch, // Stretch button
        children: [
          // Success Icon styling
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              color: AppColors.secondaryWithOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: AppColors.secondary,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.check,
                  size: 40,
                  color: Colors.white,
                ),
              ),
            ),
          ),
          SizedBox(height: 24),
          Text(
            'Keypad PIN Updated',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: AppColors.primary,
            ),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: 32.0), // Add padding for text wrapping
            child: Text(
              'The global keypad PIN has been successfully updated',
              style: TextStyle(
                fontSize: 16,
                color: Colors.grey[600],
              ),
              textAlign: TextAlign.center,
            ),
          ),
          SizedBox(height: 32),
          Padding(
            // Add padding for button width control
            padding: const EdgeInsets.symmetric(horizontal: 64.0),
            child: SizedBox(
              height: 56,
              child: ElevatedButton(
                onPressed: () => Navigator.pushNamedAndRemoveUntil(
                    context,
                    '/home',
                    (route) => false), // Go back to home and clear stack
                child: Text('Back to Home'),
              ),
            ),
          ),
        ],
      ),
    );
  }
} // End of _ChangePinScreenState
