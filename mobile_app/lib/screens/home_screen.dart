// lib/screens/home_screen.dart (Simplified Logic with video_player)

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:neuralock/utils/app_colors.dart';
import 'package:neuralock/widgets/nav_bar.dart';
import 'package:neuralock/services/api_service.dart';
import 'package:video_player/video_player.dart'; // Import video_player
import 'dart:async';

class HomeScreen extends StatefulWidget {
  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _isCameraExpanded = false; // Track expansion state
  VideoPlayerController? _videoController; // Make nullable
  final ApiService _apiService = ApiService();

  // Define Pi's IP and the streaming port (must match Pi script)
  final String _piIpAddress = "192.168.29.4"; // !! REPLACE !!
  final String _piStreamingPort =
      "8080"; // CORRECT PORT (where Flask serves /stream)
  late String _streamUrl;

  bool _isVideoInitialized = false; // Track if controller is ready to play
  bool _isProcessingAction = false; // Prevent rapid start/stop calls

  @override
  void initState() {
    super.initState();
    _streamUrl = "http://$_piIpAddress:$_piStreamingPort/stream";
    print("HomeScreen initState: Stream URL = $_streamUrl");
    // Controller will be created on demand
  }

  @override
  void dispose() {
    print("HomeScreen dispose called");
    _stopStream(); // Ensure stop is called (which includes dispose)
    super.dispose();
  }

  // --- Helper UI Methods ---
  void _showErrorSnackbar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red[600]),
    );
  }

  void _videoPlayerListener() {
    // Only update UI if mounted and controller exists/is initialized
    if (!mounted ||
        _videoController == null ||
        !_videoController!.value.isInitialized) {
      return;
    }
    // Check for errors
    if (_videoController!.value.hasError) {
      print(
          "VideoPlayer Error via Listener: ${_videoController!.value.errorDescription}");
      if (mounted) {
        setState(() {
          // Optionally update a status text variable here
          // _playerStatusText = "Error: ${_videoController!.value.errorDescription}";
        });
      }
    } else {
      // Optionally update status or just rebuild if needed
      if (mounted) {
        setState(() {
          // Update status text if using one
          // _playerStatusText = "State: ${_videoController!.value.isPlaying ? 'Playing' : 'Paused/Stopped'}";
        });
      }
    }
  }

  // Function to create, initialize, and play video
  Future<void> _createAndPlayVideoController() async {
    // Dispose previous controller if somehow exists
    if (_videoController != null) {
      await _videoController!.dispose();
      _videoController = null;
    }

    print("VideoPlayer: Creating new controller for $_streamUrl");
    _videoController = VideoPlayerController.networkUrl(Uri.parse(_streamUrl));

    try {
      print("VideoPlayer: Initializing...");
      await _videoController!.initialize().timeout(Duration(seconds: 10));
      if (!mounted) {
        _videoController?.dispose();
        return;
      } // Check after await

      print("VideoPlayer: Initialized successfully.");
      setState(() {
        _isVideoInitialized = true;
      }); // Mark as initialized

      await _videoController!.play();
      await _videoController!.setLooping(true); // Loop for MJPEG stream
      print("VideoPlayer: play() called.");
      if (mounted) setState(() {}); // Update UI to show player
    } catch (e) {
      print("VideoPlayer: Initialization/Play failed: $e");
      if (mounted) {
        _showErrorSnackbar(
            "Error playing stream: ${e.toString().split(':').last.trim()}");
        setState(() {
          _isVideoInitialized = false;
          _isCameraExpanded = false; // Collapse tile on error
        });
      }
      // Clean up failed controller
      await _videoController?.dispose();
      _videoController = null;
      // Do NOT tell Pi to stop here, as it might not have started
      // Let the _stopStream called by _onExpansionChanged handle Pi communication if needed
      throw e; // Rethrow to signal failure in _startStreaming
    }
  }

  // Function to call Pi API to start streaming and init player
  Future<void> _startStreaming() async {
    if (_isProcessingAction || _videoController != null) {
      // Prevent starting if already running/processing
      print(
          "Start Stream Aborted: Processing=$_isProcessingAction, ControllerExists=${_videoController != null}");
      return;
    }
    setState(() {
      _isProcessingAction = true;
      _isVideoInitialized = false;
    }); // Reset init flag
    print("Requesting Pi to START streaming...");
    try {
      // 1. Tell Pi to Start
      await _apiService.controlPiStream(_piIpAddress, true);
      if (!mounted) throw Exception("Widget unmounted during Pi start request");
      print("Pi stream start requested.");

      // 2. Create and Play Video Controller
      // Add small delay to allow Pi stream to become available
      await Future.delayed(Duration(milliseconds: 750));
      if (!mounted || !_isCameraExpanded)
        throw Exception(
            "Tile collapsed before player init"); // Check state again

      await _createAndPlayVideoController(); // Handles init and play

      print("Stream start sequence seems complete.");
    } catch (e) {
      if (mounted) {
        print("Error during stream start sequence: $e");
        // Error snackbar shown in _createAndPlayVideoController if it failed there
        // Ensure Pi is told to stop if we successfully told it to start
        if (_videoController == null) {
          // Check if player creation itself failed early
          try {
            await _apiService.controlPiStream(_piIpAddress, false);
          } catch (_) {}
        }
        // Collapse tile (setState is handled in _createAndPlayVideoController error or here)
        if (mounted) setState(() => _isCameraExpanded = false);
      }
    } finally {
      if (mounted)
        setState(() {
          _isProcessingAction = false;
        });
    }
  }

  // Function to call Pi API to stop streaming and dispose player
  Future<void> _stopStream() async {
    if (_isProcessingAction) {
      print("Stop Stream Aborted: Processing=$_isProcessingAction");
      return;
    }
    setState(() {
      _isProcessingAction = true;
    });
    print("Stopping stream...");

    // 1. Tell Pi to stop streaming first
    try {
      print("Requesting Pi to STOP streaming...");
      await _apiService.controlPiStream(_piIpAddress, false);
      print("Pi stream stop requested.");
    } catch (e) {
      print("Error requesting Pi to stop stream: $e");
      // Continue cleanup even if Pi command fails
    }

    // 2. Dispose local video controller
    final controllerToDispose = _videoController; // Capture instance
    if (controllerToDispose != null) {
      _videoController = null; // Set to null immediately
      if (mounted)
        setState(() {
          _isVideoInitialized = false;
        }); // Update UI flag
      try {
        controllerToDispose.removeListener(
            _videoPlayerListener); // Remove listener just in case
        await controllerToDispose.dispose();
        print("VideoPlayer: Controller disposed.");
      } catch (e) {
        print("Error disposing video controller: $e");
      }
    } else {
      print("Stop stream called but controller was already null.");
    }

    if (mounted) {
      setState(() {
        _isProcessingAction = false;
      });
    }
  }

  // Handle expansion tile state change
  void _onExpansionChanged(bool isNowExpanded) {
    print("Expansion Changed Callback: isNowExpanded = $isNowExpanded");
    if (!mounted || isNowExpanded == _isCameraExpanded) {
      print(
          "Ignoring expansion callback (already in target state or unmounted).");
      return; // Prevent action if state already matches
    }

    // Update the state FIRST
    setState(() {
      _isCameraExpanded = isNowExpanded;
      // If collapsing, immediately mark as not initialized
      if (!_isCameraExpanded) _isVideoInitialized = false;
    });

    // Trigger the corresponding action AFTER updating state
    if (isNowExpanded) {
      _startStreaming();
    } else {
      _stopStream();
    }
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
                child: SingleChildScrollView(
                  padding: EdgeInsets.all(16),
                  child: Column(
                    children: [
                      _buildCameraSection(), // Uses ExpansionTile
                      SizedBox(height: 16),
                      _buildChangePinButton(),
                      SizedBox(height: 80),
                    ],
                  ),
                ),
              ),
            ],
          ),
          // Optional Processing Overlay
          if (_isProcessingAction)
            Container(
                color: Colors.black.withOpacity(0.1),
                child: Center(child: CircularProgressIndicator())),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: NavBar(currentIndex: 0),
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
            'Home',
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

  // --- Camera Section using ExpansionTile + video_player ---
  Widget _buildCameraSection() {
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
      child: ExpansionTile(
        key: PageStorageKey<String>('cameraExpansionTile'),
        // Let onExpansionChanged control the state, don't set initiallyExpanded
        onExpansionChanged: _onExpansionChanged,
        // Use state variable to determine if it should APPEAR expanded
        // This might cause a slight visual jump if state changes rapidly,
        // but avoids conflicting control with onExpansionChanged.
        // Alternatively, remove this line and rely solely on user taps.
        // initiallyExpanded: _isCameraExpanded,
        tilePadding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        title: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Eye hole cam',
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
                'Secured',
                style: TextStyle(
                  fontSize: 12,
                  color: AppColors.primary,
                ),
              ),
            ),
          ],
        ),
        trailing: Icon(
          _isCameraExpanded
              ? Icons.keyboard_arrow_up
              : Icons.keyboard_arrow_down,
          color: AppColors.primary,
        ),
        children: <Widget>[
          Container(
            height: 200,
            color: Colors.black,
            child: Center(
              // Show Player if controller exists AND is initialized
              child: (_videoController != null &&
                      _isVideoInitialized) // Use the state flag
                  ? AspectRatio(
                      aspectRatio: _videoController!.value.aspectRatio > 0
                          ? _videoController!.value.aspectRatio
                          : 16 / 9, // Default aspect ratio if needed
                      child: VideoPlayer(_videoController!),
                    )
                  // Show placeholder/status otherwise
                  : Padding(
                      padding: const EdgeInsets.all(8.0),
                      child: _isCameraExpanded // Show spinner only if expanded
                          ? CircularProgressIndicator(strokeWidth: 2)
                          : Icon(Icons.videocam_off_outlined,
                              color: Colors.grey[700],
                              size: 50), // Placeholder when collapsed
                    ),
            ),
            // Overlays can be added back inside a Stack here if needed
          ),
        ],
      ),
    );
  }
  // --- END Camera Section ---

  Widget _buildChangePinButton() {
    // ... (Same as the original code you provided) ...
    return GestureDetector(
      onTap: () => Navigator.pushNamed(context, '/change_pin'),
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.secondaryWithOpacity(0.3)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.03),
              blurRadius: 10,
              offset: Offset(0, 2),
            ),
          ],
        ),
        child: Stack(
          children: [
            Positioned.fill(
              child: Container(
                decoration: BoxDecoration(
                  color: AppColors.secondaryWithOpacity(0.1),
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.all(16),
              child: Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: AppColors.secondary,
                      borderRadius: BorderRadius.circular(24),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.secondaryWithOpacity(0.3),
                          blurRadius: 8,
                          offset: Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Icon(
                      Icons.vpn_key,
                      color: Colors.white,
                      size: 24,
                    ),
                  ),
                  SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Change access PIN',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: AppColors.primary,
                          ),
                        ),
                        SizedBox(height: 4),
                        Text(
                          'Manage your security credentials',
                          style: TextStyle(
                            fontSize: 12,
                            color: AppColors.primaryWithOpacity(0.7),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: AppColors.secondaryWithOpacity(0.2),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Center(
                      child: Icon(
                        Icons.arrow_forward_ios,
                        color: AppColors.primary,
                        size: 14,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
} // End _HomeScreenState
