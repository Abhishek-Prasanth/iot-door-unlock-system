// lib/screens/logs_screen.dart

import 'package:flutter/material.dart';
import 'package:neuralock/utils/app_colors.dart';
import 'package:neuralock/widgets/nav_bar.dart'; // Assuming NavBar exists
import 'package:neuralock/services/api_service.dart';
import 'package:neuralock/models/log_model.dart'; // Import the Log model
import 'package:intl/intl.dart'; // For date formatting

class LogsScreen extends StatefulWidget {
  @override
  _LogsScreenState createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  List<Log> _logs = []; // Holds all fetched logs
  bool _isLoading = true; // Tracks initial loading state
  String _selectedFilter = "All"; // Current filter selection
  final List<String> _filters = [
    "All",
    "Access",
    "Intruder",
    "Keypad",
    "System"
  ]; // Available filters
  final ApiService _apiService = ApiService(); // Instance of API service

  @override
  void initState() {
    super.initState();
    _loadLogs(); // Load logs when screen initializes
  }

  // Fetch logs from the API based on the selected filter
  Future<void> _loadLogs() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
    });

    try {
      // Pass filter to API if backend supports it, otherwise filter client-side
      // Assuming API returns all logs and we filter here for simplicity now
      final logsData = await _apiService.getLogs(/* type: _selectedFilter */);
      if (!mounted) return;

      setState(() {
        // Map JSON to Log objects
        _logs = logsData.map((logData) => Log.fromJson(logData)).toList();
        // Optional: Sort logs if server doesn't guarantee order (e.g., by timestamp descending)
        // _logs.sort((a, b) => b.getDateTime().compareTo(a.getDateTime()));
      });
    } catch (e) {
      if (!mounted) return;
      _showErrorSnackbar(
          "Error loading logs: ${e.toString().replaceFirst('Exception: ', '')}");
    } finally {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });
    }
  }

  // Apply client-side filtering based on _selectedFilter
  List<Log> get _filteredLogs {
    if (_selectedFilter == "All") {
      return _logs;
    } else if (_selectedFilter == "Keypad") {
      // Combine Success and Failure for "Keypad" filter
      return _logs
          .where((log) =>
              log.type.toLowerCase() == 'keypad success' ||
              log.type.toLowerCase() == 'keypad failure')
          .toList();
    } else {
      // Filter by exact type (case-insensitive)
      return _logs
          .where(
              (log) => log.type.toLowerCase() == _selectedFilter.toLowerCase())
          .toList();
    }
  }

  // --- Helper UI Methods ---
  void _showErrorSnackbar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red[600]),
    );
  }

  // --- Build Methods ---

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          // Main Content Area
          Column(
            children: [
              _buildAppBar(), // Build the top AppBar
              _buildFilters(), // Build the horizontal filter list
              // Logs List or Loading/Empty State
              Expanded(
                child: _isLoading
                    ? Center(
                        child:
                            CircularProgressIndicator()) // Show loading spinner
                    : RefreshIndicator(
                        // Enable pull-to-refresh
                        onRefresh: _loadLogs,
                        child: _filteredLogs.isEmpty
                            ? _buildEmptyState() // Show empty state if no logs match filter
                            : _buildLogsList(), // Build the list of logs
                      ),
              ),
            ],
          ),

          // Bottom Navigation Bar
          Positioned(
            left: 0, right: 0, bottom: 0,
            child: NavBar(currentIndex: 1), // Assuming Logs is index 1
          ),
        ],
      ),
    );
  }

  // Builds the top AppBar
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
            'Activity Logs',
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

  // Builds the horizontal filter chips
  Widget _buildFilters() {
    return Container(
      height: 50,
      padding: EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 5,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        itemCount: _filters.length,
        itemBuilder: (context, index) {
          final filter = _filters[index];
          final isSelected = _selectedFilter == filter;

          return GestureDetector(
            onTap: () {
              setState(() {
                _selectedFilter = filter;
              });
              // Optional: Call _loadLogs() here if API supports filtering,
              // otherwise client-side filtering handles it automatically
            },
            child: Container(
              margin: EdgeInsets.symmetric(horizontal: 4, vertical: 10),
              padding: EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: isSelected ? AppColors.primary : Colors.grey[100],
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                    color: isSelected ? AppColors.primary : Colors.grey[300]!,
                    width: 1),
              ),
              child: Center(
                child: Text(
                  filter,
                  style: TextStyle(
                      color: isSelected ? Colors.white : Colors.grey[700],
                      fontWeight:
                          isSelected ? FontWeight.w600 : FontWeight.normal,
                      fontSize: 13),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  // Builds the placeholder shown when no logs match the filter
  Widget _buildEmptyState() {
    return LayoutBuilder(builder: (context, constraints) {
      return SingleChildScrollView(
        physics: AlwaysScrollableScrollPhysics(),
        child: Container(
          height: constraints.maxHeight,
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    color: Colors.grey[100],
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    Icons.history_toggle_off,
                    size: 40,
                    color: Colors.grey[400],
                  ),
                ),
                SizedBox(height: 16),
                Text(
                  'No logs found',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                    color: Colors.grey[700],
                  ),
                ),
                SizedBox(height: 8),
                Text(
                  _selectedFilter == "All"
                      ? 'Activity logs will appear here'
                      : 'No $_selectedFilter logs available',
                  style: TextStyle(
                    color: Colors.grey[500],
                  ),
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: 24),
                ElevatedButton.icon(
                  onPressed: _loadLogs,
                  icon: Icon(
                    Icons.refresh,
                    size: 18,
                  ),
                  label: Text('Refresh'),
                  style: ElevatedButton.styleFrom(
                    padding: EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                  ),
                ),
                SizedBox(height: 80), // Space for nav bar
              ],
            ),
          ),
        ),
      );
    });
  }

  // Builds the scrollable list of log entries, grouped by date
  Widget _buildLogsList() {
    Map<String, List<Log>> groupedLogs = {};

    // Group logs by date client-side
    for (var log in _filteredLogs) {
      groupedLogs.putIfAbsent(log.date, () => []).add(log);
    }
    // Get list of dates (keys)
    List<String> sortedDates = groupedLogs.keys.toList();
    // Optional: Sort dates descending (newest first) if server doesn't
    // Requires robust date parsing
    // sortedDates.sort((a, b) { /* ... date comparison logic ... */ });

    return ListView.builder(
      padding:
          EdgeInsets.fromLTRB(16, 16, 16, 96), // Bottom padding for nav bar
      itemCount: sortedDates.length, // Number of dates (groups)
      itemBuilder: (context, dateIndex) {
        // dateIndex is available here
        final date = sortedDates[dateIndex];
        final logsForDate = groupedLogs[date]!;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // --- Corrected Call: Pass dateIndex ---
            _buildDateHeader(date, dateIndex),
            // ------------------------------------
            SizedBox(height: 8),
            // Log Items for this date (using nested ListView.builder)
            ListView.builder(
                shrinkWrap: true, // Essential for nested lists
                physics:
                    NeverScrollableScrollPhysics(), // Disable nested scrolling
                itemCount: logsForDate.length,
                itemBuilder: (context, logIndex) {
                  final log = logsForDate[logIndex];
                  return _buildLogItem(log); // Build individual log item card
                }),
            // Add spacing between date groups, except after the last one
            if (dateIndex < sortedDates.length - 1) SizedBox(height: 16),
          ],
        );
      },
    );
  }

  // Builds the date header (e.g., "Today", "Yesterday", "Month Day, Year")
  // --- Corrected Definition: Accepts dateIndex ---
  Widget _buildDateHeader(String dateString, int dateIndex) {
    String formattedDate = dateString; // Default to original string
    try {
      // Parse date string assuming MM/DD/YYYY format from server
      final dateParts = dateString.split('/');
      if (dateParts.length == 3) {
        final parsedDate = DateTime(int.parse(dateParts[2]),
            int.parse(dateParts[0]), int.parse(dateParts[1]));
        final now = DateTime.now();
        final today = DateTime(now.year, now.month, now.day);
        final yesterday = today.subtract(Duration(days: 1));

        if (parsedDate == today)
          formattedDate = 'Today';
        else if (parsedDate == yesterday)
          formattedDate = 'Yesterday';
        else
          formattedDate =
              DateFormat('MMMM d, yyyy').format(parsedDate); // Use intl package
      }
    } catch (e) {
      print("Error parsing date header: $e");
      // Keep original date string if parsing fails
    }

    return Padding(
      // Use the passed dateIndex for conditional top padding
      padding: EdgeInsets.only(left: 8, top: dateIndex == 0 ? 0 : 16),
      child: Text(
        formattedDate,
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: Colors.grey[700],
        ),
      ),
    );
  }
  // ------------------------------------------------

  // Builds a single log item card
  Widget _buildLogItem(Log log) {
    final bool isIntruder = log.type.toLowerCase() == 'intruder';
    final iconData = _getLogTypeIcon(log.type);
    final iconColor = _getLogTypeColor(log.type);
    final title = _getLogTypeTitle(log.type);

    return Container(
      margin: EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.04),
              blurRadius: 8,
              offset: Offset(0, 1),
            ),
          ],
          border: Border.all(color: Colors.grey[200]!, width: 0.5)),
      child: Column(
        children: [
          // Log Header Row
          Padding(
            padding: EdgeInsets.all(12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Icon
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: iconColor.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Center(
                    child: Icon(
                      iconData,
                      color: iconColor,
                      size: 20,
                    ),
                  ),
                ),
                SizedBox(width: 12),
                // Title and Details
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                            fontWeight: FontWeight.w600,
                            color: Colors.grey[850],
                            fontSize: 15),
                      ),
                      SizedBox(height: 3),
                      Text(
                        log.details,
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.grey[600],
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                SizedBox(width: 8),
                // Timestamp
                Padding(
                  padding: const EdgeInsets.only(top: 2.0),
                  child: Text(
                    log.timestamp,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey[500],
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Conditional User/Intruder Image Section
          if (log.user != null || (isIntruder && log.imagePath != null)) ...[
            Divider(height: 1, color: Colors.grey[200]),
            // User Info Row
            if (log.user != null)
              Padding(
                padding: EdgeInsets.fromLTRB(12, 8, 12, 8),
                child: Row(
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: Colors.grey[300]!,
                        ),
                      ),
                      child: ClipRRect(
                          borderRadius: BorderRadius.circular(16),
                          child: Image.network(
                              _apiService.getImageUrl(log.user!["avatar"]),
                              fit: BoxFit.cover,
                              errorBuilder: (c, e, s) => Center(
                                  child: Icon(Icons.person,
                                      size: 20, color: Colors.grey[400])))),
                    ),
                    SizedBox(width: 8),
                    Text(
                      log.user!["name"] ?? 'Unknown User',
                      style: TextStyle(
                        fontSize: 13,
                        color: Colors.grey[700],
                      ),
                    ),
                  ],
                ),
              ),
            // Intruder Image Display
            if (isIntruder && log.imagePath != null)
              Container(
                height: 150,
                width: double.infinity,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.only(
                    bottomLeft: Radius.circular(12),
                    bottomRight: Radius.circular(12),
                  ),
                  color: Colors.grey[200],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.only(
                    bottomLeft: Radius.circular(12),
                    bottomRight: Radius.circular(12),
                  ),
                  child: Image.network(
                    _apiService
                        .getImageUrl(log.imagePath), // Use helper for full URL
                    fit: BoxFit.cover,
                    loadingBuilder: (context, child, progress) => progress ==
                            null
                        ? child
                        : Center(
                            child: CircularProgressIndicator(strokeWidth: 2)),
                    errorBuilder: (context, error, stackTrace) => Center(
                      child: Icon(
                        Icons.error_outline,
                        size: 40,
                        color: Colors.grey[400],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }

  // Helper to get icon based on log type
  IconData _getLogTypeIcon(String type) {
    switch (type.toLowerCase()) {
      case 'access':
        return Icons.lock_open_rounded;
      case 'intruder':
        return Icons.warning_amber_rounded;
      case 'keypad success':
        return Icons.dialpad_rounded;
      case 'keypad failure':
        return Icons.dialpad_rounded;
      case 'system':
        return Icons.settings_suggest_outlined;
      default:
        return Icons.info_outline;
    }
  }

  // Helper to get color based on log type
  Color _getLogTypeColor(String type) {
    switch (type.toLowerCase()) {
      case 'access':
        return Colors.green.shade600;
      case 'intruder':
        return Colors.red.shade600;
      case 'keypad success':
        return Colors.blue.shade600;
      case 'keypad failure':
        return Colors.orange.shade700;
      case 'system':
        return Colors.purple.shade600;
      default:
        return Colors.grey.shade600;
    }
  }

  // Helper to get display title based on log type
  String _getLogTypeTitle(String type) {
    switch (type.toLowerCase()) {
      case 'access':
        return 'Door Access';
      case 'intruder':
        return 'Intruder Alert';
      case 'keypad success':
        return 'Keypad Unlock';
      case 'keypad failure':
        return 'Keypad Failed';
      case 'system':
        return 'System Event';
      default:
        return type;
    }
  }
} // End of _LogsScreenState
