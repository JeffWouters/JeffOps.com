---
weight: 10
title: "How to Test Architecture in .NET with NetArchTest"
date: 2023-11-13T00:00:01+08:00
lastmod: 2023-11-13T00:00:01+08:00
draft: false
author: "JeffOps"
authorLink: "https://jeffwouters.nl"
description: "How to Test Architecture in .NET with NetArchTest"
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["DotNET","NetArchTest"]
categories: ["blog"]

hiddenFromHomePage: false
---

Have you ever wondered how to ensure that your .NET code follows the architectural design and conventions that you have chosen? Do you want to avoid the common pitfalls of violating the principles of separation of concerns, dependency inversion, or layering? If so, then you might be interested in NetArchTest, a fluent API for .NET Standard that can enforce architectural rules in unit tests.

Rcentely I stumbled upon the [NetArchTest package by Ben Morris](https://github.com/BenMorris/NetArchTest).

## What is NetArchTest?

NetArchTest is a .NET library that allows you to create tests that enforce conventions for class design, naming, and dependency in .NET code bases. It is inspired by the ArchUnit library for Java¹. It uses a fluid API that allows you to string together readable rules that can be used in test assertions. You can use it with any unit test framework and incorporate it into your build pipeline.

It is available as a [NuGet package](https://www.nuget.org/packages/NetArchTest.Rules).

## How to use NetArchTest?

The basic steps to use NetArchTest are:

1. Select a set of types from a path, assembly, or namespace using the static `Types` class.
2. Filter the types using one or more predicates, such as `ResideInNamespace`, `HaveDependencyOn`, `ImplementInterface`, etc. You can chain the predicates using `And` or `Or` conjunctions.
3. Apply one or more conditions using the `Should` or `ShouldNot` methods, such as `BeSealed`, `BeAbstract`, `HaveNameStartingWith`, etc.
4. Obtain a result from the rule by using an executor, such as `GetTypes` to return the types that match the rule or `GetResult` to determine whether the rule has been met. The result will also return a list of types that failed to meet the conditions.

Here are some examples of rules that you can create with NetArchTest:

- Classes in the presentation layer should not directly reference repositories:

```csharp
var result = Types.InCurrentDomain()
    .That()
    .ResideInNamespace("MyProject.Presentation")
    .ShouldNot()
    .HaveDependencyOn("MyProject.Data")
    .GetResult()
    .IsSuccessful;
```

- Classes in the data layer should implement `IRepository`:

```csharp
var result = Types.InCurrentDomain()
    .That()
    .ResideInNamespace("MyProject.Data")
    .Should()
    .ImplementInterface(typeof(IRepository))
    .GetResult()
    .IsSuccessful;
```

- All the service classes should be sealed:

```csharp
var result = Types.InCurrentDomain()
    .That()
    .ImplementInterface(typeof(IService))
    .Should()
    .BeSealed()
    .GetResult()
    .IsSuccessful;
```

## Want to read more on its origin?
Ben's written a nice blog post about how he came to write this package. Especially if you're interrested in what motivates people, and the path they've walked, take a look at his [blog post](https://www.ben-morris.com/writing-archunit-style-tests-for-net-and-c-for-self-testing-architectures/).

## Why use NetArchTest?

NetArchTest can help you to:

- Maintain the consistency and quality of your code base over time.
- Avoid the need for manual code reviews or static analysis tools that may not capture your specific architectural requirements.
- Create a self-testing architecture that can be verified by automated tests.
- Communicate and document your architectural design and conventions through code.

## Conclusion

NetArchTest is a powerful and easy-to-use library that can help you to test your architecture in .NET. It can help you to enforce the rules and conventions that you have chosen for your code base and avoid the common pitfalls of architectural decay. You can use it with any unit test framework and integrate it into your build pipeline. If you are interested in learning more about NetArchTest, you can check out its GitHub repository or its NuGet page. Happy testing!