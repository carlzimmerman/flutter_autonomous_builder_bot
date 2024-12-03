import 'package:flutter/material.dart';

class TodoListScreen extends StatelessWidget {
  final List<String> _todoItems = [
    'Buy groceries',
    'Walk the dog',
    'Read a book',
    'Call mom',
    'Finish homework'
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('To-Do List'),
      ),
      body: ListView.builder(
        itemCount: _todoItems.length,
        itemBuilder: (context, index) {
          return ListTile(
            title: Text(_todoItems[index]),
          );
        },
      ),
    );
  }
}