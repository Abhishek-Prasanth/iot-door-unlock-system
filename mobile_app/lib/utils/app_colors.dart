import 'package:flutter/material.dart';

class AppColors {
  // Primary colors
  static const Color primary = Color(0xFF00576B);
  static const Color primaryLight = Color(0xFF006D85);
  static const Color secondary = Color(0xFF99BC85);

  // Background colors
  static const Color background = Color(0xFFF8FAFC);
  static const Color cardBackground = Colors.white;

  // Text colors
  static const Color textPrimary = Color(0xFF334155);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color textLight = Color(0xFF94A3B8);

  // Status colors
  static const Color success = Color(0xFF10B981);
  static const Color warning = Color(0xFFF59E0B);
  static const Color error = Color(0xFFEF4444);

  // Utility colors
  static const Color divider = Color(0xFFE2E8F0);
  static const Color overlay = Color(0x80000000);

  // Opacity variants for primary and secondary
  static Color primaryWithOpacity(double opacity) =>
      primary.withOpacity(opacity);
  static Color secondaryWithOpacity(double opacity) =>
      secondary.withOpacity(opacity);
}
