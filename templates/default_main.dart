// default_main.dart
import 'package:flutter/material.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter App Template',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      home: const Scaffold(  // Default home until routes are added
        body: Center(
          child: Text('Welcome to the Flutter Autonomous Builder Bot'),
        ),
      ),
      routes: {
        // Dynamic routes will be added here
      },
    );
  }
}