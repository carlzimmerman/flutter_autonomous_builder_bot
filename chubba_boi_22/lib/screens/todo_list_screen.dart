import 'package:flutter/material.dart';

class TodoListScreen extends StatelessWidget {
  final List<String> todos = [
    'Buy groceries',
    'Walk the dog',
    'Read a book'
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Todo List'),
      ),
      body: ListView.builder(
        itemCount: todos.length,
        itemBuilder: (context, index) {
          return ListTile(
            title: Text(todos[index]),
          );
        },
      ),
    );
  }
}