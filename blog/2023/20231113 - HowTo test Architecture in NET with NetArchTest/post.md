---
tags: [dotnet, netarchtest, architecture, testing, dev]
slug: howto-test-architecture-in-dotnet-with-netarchtest
canonical: https://jeffops.com/posts/2023/howto-test-architecture-in-dotnet-with-netarchtest/
---

# HowTo test Architecture in .NET with NetArchTest

Have you ever wondered how to ensure that your .NET code follows the architectural design and conventions that you have chosen? Do you want to avoid the common pitfalls of violating the principles of separation of concerns, dependency inversion, or layering? If so, then you might be interested in NetArchTest, a fluent API for .NET Standard that can enforce architectural rules in unit tests.

Recently I stumbled upon the NetArchTest package by Ben Morris.

## What is NetArchTest?

NetArchTest is a .NET library that allows you to create tests that enforce conventions for class design, naming, and dependency in .NET code bases. It is inspired by the ArchUnit library for Java. It uses a fluid API that allows you to string together readable rules that can be used in test assertions. You can use it with any unit test framework and incorporate it into your build pipeline.

It is available as a NuGet package.

## How to use NetArchTest?

The basic steps to use NetArchTest are:

1. Select a set of types from a path, assembly, or namespace using the static `Types` class.
2. Filter the types using one or more predicates, such as `ResideInNamespace`, `HaveDependencyOn`, `ImplementInterface`, etc. You can chain the predicates using `And` or `Or` conjunctions.
3. Apply one or more conditions using the `Should` or `ShouldNot` methods, such as `BeSealed`, `BeAbstract`, `HaveNameStartingWith`, etc.
4. Obtain a result from the rule by using an executor, such as `GetTypes` to return the types that match the rule or `GetResult` to determine whether the rule has been met. The result will also return a list of types that failed to meet the conditions.

Here are some examples of rules that you can create with NetArchTest:

Classes in the presentation layer should not directly reference repositories:

```csharp
var result = Types.InCurrentDomain()
    .That()
    .ResideInNamespace("MyProject.Presentation")
    .ShouldNot()
    .HaveDependencyOn("MyProject.Data")
    .GetResult()
    .IsSuccessful;
```

Classes in the data layer should implement `IRepository`:

```csharp
var result = Types.InCurrentDomain()
    .That()
    .ResideInNamespace("MyProject.Data")
    .Should()
    .ImplementInterface(typeof(IRepository))
    .GetResult()
    .IsSuccessful;
```

All the service classes should be sealed:

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

Ben's written a nice blog post about how he came to write this package. Especially if you're interested in what motivates people, and the path they've walked, take a look at his blog post.

## Why use NetArchTest?

NetArchTest can help you to:

- Maintain the consistency and quality of your code base over time.
- Avoid the need for manual code reviews or static analysis tools that may not capture your specific architectural requirements.
- Create a self-testing architecture that can be verified by automated tests.
- Communicate and document your architectural design and conventions through code.

## Conclusion

NetArchTest is a powerful and easy-to-use library that can help you to test your architecture in .NET. It can help you to enforce the rules and conventions that you have chosen for your code base and avoid the common pitfalls of architectural decay. You can use it with any unit test framework and integrate it into your build pipeline. If you are interested in learning more about NetArchTest, you can check out its GitHub repository or its NuGet page. Happy testing!
